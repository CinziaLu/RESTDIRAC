
from tornado import web, gen
from RESTDIRAC.RESTSystem.Base.RESTHandler import RESTHandler, WErr, WOK
from RESTDIRAC.RESTSystem.Client.OAToken import OAToken
from DIRAC.ConfigurationSystem.Client.Helpers import Registry
from RESTDIRAC.ConfigurationSystem.Client.Helpers.RESTConf import getCodeAuthURL

class AuthHandler( RESTHandler ):

  ROUTE = "/oauth2/(auth|groups)"
  REQUIRE_ACCESS = False
  __oaToken = OAToken()

  def post( self, *args, **kwargs ):
    return self.get( *args, **kwargs )

  @web.asynchronous
  def get( self, reqType ):
    #Show available groups for certificate
    if reqType == "groups":
      return self.groupsAction()
    elif reqType == "auth":
      return self.authAction()

  def groupsAction( self ):
      result = self.__getGroups()
      if not result.ok:
        self.log.error( result.msg )
        self.send_error( result.code )
        return
      self.finish( result.data )
      return

  @gen.engine
  def authAction( self ):
    #Auth
    args = self.request.arguments
    respType = False
    if 'response_type' in args and args[ 'response_type' ][0] == 'code':
      respType = 'code'
    if 'grant_type' in args and args[ 'grant_type' ][0] == 'client_credentials':
      if respType:
        #Already defined a response type
        self.send_error( 400 )
        return
      respType = 'client_credentials'
    if not respType:
      #Bad request
      self.send_error( 400 )
      return
    #Start of Code request
    if respType == "code":
      try:
        cid = args[ 'client_id' ]
      except KeyError:
        self.send_error( 400 )
        return
      self.redirect( "%s?%s" % ( getCodeAuthURL(), self.request.query ) )
    elif respType == "client_credentials":
      result = yield( self.threadTask( self.__clientCredentialsRequest ) )
      if not result.ok:
        self.log.error( result.msg )
        raise result
      self.finish( result.data )
    elif respType in ( "token", "password" ):
      #Not implemented
      self.send_error( 501 )
    else:
      #ERROR!
      self.send_error( 400 )


  def __getGroups( self, DN = False ):
    if not DN:
      credDict = self.getClientCredentials()
      if not credDict:
        return WErr( 401, "No certificate received to issue a token" )
      DN = credDict[ 'subject' ]
      if not credDict[ 'validDN' ]:
       return WErr( 401, "Unknown DN %s" % DN )
    result = Registry.getGroupsForDN( DN )
    if not result[ 'OK' ]:
      return WErr( 500, result[ 'Message' ] )
    return WOK( { 'groups' : result[ 'Value' ] } )

  def __clientCredentialsRequest( self ):
    args = self.request.arguments
    try:
      group = args[ 'group' ][0]
    except KeyError:
      return WErr( 400, "Missing user group" )
    try:
      setup = args[ 'setup' ][0]
    except KeyError:
      return WErr( 400, "Missing setup" )
    credDict = self.getClientCredentials()
    if not credDict:
      return WErr( 401, "No certificate received to issue a token" )
    DN = credDict[ 'subject' ]
    if not credDict[ 'validDN' ]:
      return WErr( 401, "Unknown DN %s" % DN )
    #Check group
    result = self.__getGroups( DN )
    if not result.ok:
      return result
    groups = result.data[ 'groups' ]
    if group not in groups:
      return WErr( 401, "Invalid group %s for %s (valid %s)" % ( group, DN, groups ) )
    scope = False
    if 'scope' in args:
      scope = args[ 'scope' ]
    result = self.__oaToken.generateToken( DN, group, setup, scope = scope, renewable = False )
    if not result[ 'OK' ]:
      return WErr( 500, "Error generating token: %s" % result[ 'Message' ] )
    data = result[ 'Value' ][ 'Access' ]
    res = {}
    for ki, ko in ( ( "LifeTime", "expires_in" ), ( 'Token', 'token' ) ):
      if ki in data:
        res[ ko ] = data[ ki ]

    return WOK( res )

