# BeautifulSoup is for parsing HTML
#from BeautifulSoup import BeautifulSoup
import httplib
import urllib
import urlparse
import re
import socket
import os.path
import gzip
import StringIO
import time
import random


def get_part_of_page(resp, sub, bytes_before, bytes_after, chunk_size=1028):
    """ Look for substring "sub" in the HTTPResponse "resp", stopping early if needed.
    Tries to return a section of the page which starts "bytes_before" bytes before sub and ends "bytes_after" bytes after sub.
    If sub was found, function returns (True, section_of_page)
    If sub was not found, function returns (False, entire_page)
    This returns it as a str!
    """
    chunks = []
    """The chunks we get from get_page_chunks_slowly"""
    num_chunks_to_cat = int(len(sub) / chunk_size) + 2
    """Number of chunks to concat together to make sure we find sub, even if it's over the edge of a chunk"""
    while True:
        chunk = resp.read(chunk_size)
        if not chunk:
            break
        chunks.append(chunk)
        search_from_chunk = len(chunks)-num_chunks_to_cat
        """Start searching from this chunk"""
        haystack = ''.join(chunks[search_from_chunk:])
        try:
            index = haystack.index(sub)
        except ValueError:
            continue
        else:
            bytes_to_end_of_haystak = len(haystack) - index - len(sub)
            extra_bytes_to_download = bytes_after - bytes_to_end_of_haystak
            # expand towards the start of the file
            while index < bytes_before and search_from_chunk > 0:
                search_from_chunk -= 1
                index += len(chunks[search_from_chunk])
                haystack = chunks[search_from_chunk] + haystack
            # trim the start to bytes_before bytes
            if index > bytes_before:
                haystack = haystack[index-bytes_before:]
            else:
                bytes_before = index
            if extra_bytes_to_download > 0:
                data = resp.read(extra_bytes_to_download)
                if data:
                    haystack += data
            if extra_bytes_to_download < 0:
                # extra_bytes_to_download here is -ve so trims to end of heystack
                haystack = haystack[:extra_bytes_to_download]
            return (True, haystack)
    return (False, ''.join(chunks))

class BrowserHTTP( Exception ): pass

class TooManyRetries( Exception ): pass

class Redirect(Exception):
    """
    Common code for internal and external redirects
    """
    def __init__(self, location, status, reason, response, http_or_https):
        self.location = location
        self.status = status
        self.reason = reason
        self.response = response
        self.secure = (http_or_https == 'https')
    def info(self):
        return "%s %s (to %s)" % (self.status, self.reason, self.location)
    def __str__(self):
        return "Redirect, base class only: %s" % self.info()

class LocalRedirect(Redirect):
    def __str__(self):
        return "LocalRedirect: %s" % self.info()

class ExternalRedirect(Redirect):
    def __str__(self):
        return "ExternalRedirect: %s" % self.info()
    def host(self):
        host, _ = urllib.splithost(self.location.split(":",1)[-1])
        return host


def url_join(old_location, new_location):
    ''' Join to create a path URL from an old and a new location. For example:
    url_join('/foo/baz', 'foo.htm') -> '/foo/foo.htm' '''
    if new_location.startswith('/'):
        return new_location
    else:
        # fix the URL ourselves
        # this is a relative URL, so add the previous location
        if new_location.startswith('?'):
            ques = old_location.rfind('?')
            if ques > 0:
                base_location = old_location[:ques]
            else:
                base_location = old_location
            location = '%s%s' % (base_location, new_location)
        else:
            base_location = old_location[:old_location.rfind('/')]
            location = '%s/%s' % (base_location, new_location)
        # fix spaces that sometimes appear
        location = location.replace(' ', '+')
        # normalise the path
        location = os.path.abspath(location)
        return location

def get_content_type_and_encoding(content_type_header):
    """ Returns (content_type, encoding), (content_type, None) or (None, None)"""
    if not content_type_header: return (None, None)
    h_parts = content_type_header.split(';')
    content_type = h_parts[0]
    page_encoding = None
    for h_part in h_parts[1:]:
        h_part = h_part.strip()
        if h_part.lower().startswith('charset='):
            page_encoding = h_part[8:]
    return (content_type, page_encoding,)


_rexp  = re.compile( r'expires=\w{3},[^;,]+[;,]?' )
_rpath = re.compile( r'(path|domain)=[^;,]*[;,]?' )
_rhttpOnly = re.compile( r'HttpOnly,?' )

class CookieJar(dict):
    """ The cookie jar handles session cookies.  Tries to be RFC2109 compliant """
    def add( self, cookie_string ):
        """ Parse cookie string and add to jar """
        ### remove expires, path and domain options from string
        ( cookie_string, n ) = _rexp.subn( '', cookie_string )
        ( cookie_string, n ) = _rpath.subn( '',  cookie_string )
        ## also ignore HttpOnly option
        ( cookie_string, n ) = _rhttpOnly.subn( '', cookie_string )
        items = re.split( '\s*;\s*', cookie_string )
        for i in items:
            if i and i.lower() != 'secure':
                if '=' in i:
                    (name, value) = i.split('=', 1)
                    self[name] = value
                else:
                    print 'Cannot understand this cookie:'
                    print i
    def header( self ):
        """ Returns cookies in string format.  """
        return '; '.join( [ '='.join(i) for i in self.items() ] )


class Browser(object):
    REDIRECT_LIMIT = 10
    SECURE = False
    def __init__( self, site, debug=False, encoding=None, guess_encoding=False, requests_before_reconnect=0, print_requests=True):
        """
        A HTTP web browser.
        When using get_page, the result will be encoded using "encoding", if given. If
        "guess encoding" is set to true, then the browser will check the http content-type
        header.
        
        """
        object.__init__(self)
        self.debug = debug
        self.encoding = encoding
        self.guess_encoding = guess_encoding
        self.add_referer = False
        self.redirect_automatically = True
        self.print_requests = print_requests
        if requests_before_reconnect > 0:
            self.requests_before_reconnect = requests_before_reconnect
            self.requests_count = 1
        else:
            self.requests_before_reconnect = -1
        self.headers = {
            "User-Agent"      : "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)",
        }
        self.https = None
        self.http = None
        # setup_browser_for_site needs to set up properly
        self.__site = site
        self.reset()
        self.setup_browser_for_site(site)
        print(self.http)
    def __get_site(self):
        return self.__site
    def __set_site(self, site):
        self.setup_browser_for_site(site)
    site = property(__get_site, __set_site, doc="The hostname of the browser. You can safely change this value!")
    def setup_browser_for_site(self, site):
        """ Sets up the browser to connect to the specified site """
        # for self.site property
        self.__site = site
        # clear 
        self.last_visited = None
        self.cookies = CookieJar()
        #  Create a connection object for plain HTTP and secure connections.  HTTPlib does not open a connection
        #  at this point, so we lose little if we never use one or other of these objects.
        self.reset() # makes the self.http and self.https 
    def __repr__(self):
        extra_data = []
        if self.encoding or self.guess_encoding:
            extra_data.append("using %s %s" % (self.guess_encoding and 'guessed encoding' or 'encoding', self.encoding or 'str',))
        if self.add_referer:
            extra_data.append("with referer")
        return '<Browser for %s %s>' % ( self.site, ' '.join(extra_data) ) 
    def copy(self):
        b = Browser( self.site, debug=self.debug, encoding=self.encoding, guess_encoding=self.guess_encoding, requests_before_reconnect=self.requests_before_reconnect )
        b.headers = self.headers
        b.cookies = self.cookies
        return b 
    def _add_referer(self, headers):
        if self.add_referer and self.last_visited:
            if 'Referer' in headers:
                print "Not adding referer, one was explicitly given"
            else:
                headers['Referer'] = self.last_visited 
    def post( self, location, params, raw=False, headers=dict(), secure=None, get_params=None ):
        """
        Makes a POST request, returning the http request object
        get = get parameters
        params = post parameters
        """
        if secure is None:
            secure = self.SECURE
        if not raw:
            params = urllib.urlencode( params )
        if get_params:
            location = '%s?%s' % (location, urllib.urlencode(get_params))
        headers = dict( self.headers, Cookie=self.cookies.header(), **headers )   # Merge various header sources.
        self._add_referer(headers)
        if not headers.get( 'Content-Type', None ):
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        try:
            return self.request( 'POST', location, params, headers, secure )
        except LocalRedirect, e:
            if self.redirect_automatically:
                get_headers = dict(headers)
                get_headers.pop('Content-Type')
                get_headers.pop('Cookie') # this will be added again
                location = url_join(location, e.location)
                return self.get(location, None, get_headers, e.secure)
            else:
                raise
    def get( self, location, params=None, headers=dict(), secure=None ):
        """
        Makes a GET request, returning the http request object
        """
        if secure is None:
            secure = self.SECURE
        if params:
            location = "%s?%s" % ( location, urllib.urlencode( params ) )
        headers = dict( self.headers, Cookie=self.cookies.header(), **headers )   # Merge various header sources.
        self._add_referer(headers)
        for attempts in xrange(self.REDIRECT_LIMIT):
            try:
                return self.request( 'GET', location, None, headers, secure )
            except LocalRedirect, e:
                if self.redirect_automatically:
                    location = url_join(location, e.location)
                    secure = e.secure
                    #need to update cookies in header in case of redirect
                    headers['Cookie'] = self.cookies.header()
                    continue
                else:
                    raise
        raise Exception("Browser is redirecting without end.")
    #def get_page_dom(self, *nargs, **kargs): return BeautifulSoup(self.get_page(*nargs, **kargs))
    def get_page(self, *nargs, **kargs):
        """
        Requests a page, returning as unicode if an encoding is provided here or in __init__.
        If the post parameter is used, a POST request is made, otherwise a GET is made.
        Other parameters are passed on to self.get() or self.post()
        Parameters are:
            url:     a path, eg '/index.php'
            post:    a dictionary, string or list of tuple pairs for POST data (unlike self.post(), the
                     raw parameter is not needed)
            params:  a dictionary or list of tuple pairs to be used as a query. For GET only
            headers: extra HTTP headers
        Get makes gzipped requests.
        """
        return self.get_page_extra( *nargs, **kargs )['page']
    def get_page_extra(self, url, params=None, post=None, encoding=None, headers=dict(), **args):
        """
        Same as get_page but returns a dict with more information
        """
        request_start_time = time.time()
        # Add gzip header
        if not 'Accept-Encoding' in headers:
            headers['Accept-Encoding'] = 'gzip, identity'
        # allow get=foo as an alias of params=foo.
        if ('get' in args) and (params is None):
            params = args.pop('get')
        if not (post is None):
            resp = self.post(url, post, raw=not (isinstance(post, dict) or isinstance(post, tuple)) , headers=headers, get_params=params, **args)
        else:
            resp = self.get(url, params=params, headers=headers, **args)
        if resp.getheader('Content-Encoding') == "gzip":
            sio = StringIO.StringIO( resp.read() )
            gzf = gzip.GzipFile(fileobj = sio)
            page = gzf.read()
        else:
            page = resp.read()
        # Get encoding of page
        content_type, page_encoding, = get_content_type_and_encoding(resp.getheader('Content-Type'))
        # Provide encoding if none given
        if not encoding:
            encoding = self.encoding
            if self.guess_encoding and page_encoding:
                encoding = page_encoding
        # encode
        if encoding and page:
            can_encode = True
            if content_type is None:
                can_encode = False
            elif content_type.startswith('text/'):
                can_encode = True
            elif content_type.startswith('application/'):
                # assume it's text (normally application/javascript
                can_encode = True
                if content_type in ('application/zip', 'application/x-zip-compressed',):
                    can_encode = False
            else:
                # Some non-text type
                can_encode = False
            if can_encode:
                try:
                    page = unicode( page, encoding )
                except UnicodeError:
                    print "** UNICODE ERROR when encoding type \"%s\" **" % content_type
                    print "WARNING: the text will be of type str"
            else:
                print "WARNING: Not encoding in get_page because content is of type \"%s\"" % content_type
        if self.debug:
            print 'ENCODING', encoding
        if self.print_requests:
            print "get_page: %.1f sec" % (time.time() - request_start_time,)
        return {
            'page'          : page,
            'headers'       : dict(resp.getheaders()),
            'encoding'      : encoding,
            'status'        : resp.status,
            'reason'        : resp.reason,
            'location'      : resp.location,
            'content_type'  : content_type,
            'page_encoding' : page_encoding,
            'http_status'   : resp.status,
            'http_reason'   : resp.reason,
            }
    def search_in_download(self, url, sub, bytes_before, bytes_after, encoding=None):
        """ GETs "url", searching for substring "sub". Returns "sub" and bytes_before/bytes_after bytes before/after it. Returns (True, section_of_page) on success or (False, entire_page) if "sub" is not found on the page. """
        resp = self.get(url)
        content_type, page_encoding, = get_content_type_and_encoding(resp.getheader('Content-Type'))
        if not encoding:
            encoding = self.encoding
            if self.guess_encoding and page_encoding:
                encoding = page_encoding
        did_find, page, = get_part_of_page(
            resp = resp,
            sub = sub,
            bytes_before = bytes_before,
            bytes_after = bytes_after,
            chunk_size = 2048, )
        if not resp.isclosed():
            # close the http connection, so we make a new one next time.
            # This means we will ignore any unread data
            resp.close()
            self.http.close() 
        if encoding:
            try:
                page = unicode(page, encoding)
            except UnicodeError, e:
                print "UNICODE ERROR: %r" % (e,)
                print "Unicode error while searching %r for %r" % (url, sub,) 
        return (did_find, page)
    
    def get_page_retry(self, *a, **b):
        """ tries get page several times; retrying if there is a socket error """
        retry_count = int(b.pop('retry', 3))
        timeout = int(b.pop('timeout', 1)) 
        for i in xrange(retry_count):
            if i != 0:
                print 'Will retry (%d) in %d seconds' % (i, timeout)
                self.reset()
                time.sleep(timeout)
            try:
                text = self.get_page(*a, **b)
            except socket.error, e:
                print 'Socket failure', str(e)
                continue
            if '<H2>The requested URL could not be retrieved</H2>' in text:
                reason = "unknown reason"
                for excuse in (
                    '(104) Connection reset by peer',
                    '(111) Connection refused',
                    ):
                    if excuse in text:
                        reason = excuse
                        break
                print "SQUID failed because %r" % (reason,)
                continue
            return text
        # for loop failed:
        raise TooManyRetries("Too many tries to download page - socket error") 
    def request( self, method, location, parameters, headers, secure ):
        """
        Generic function for making a HTTP request. Does HTTP redirection and
        cookies. Returns HTTP request object
        """
        if self.print_requests:
            print "%s %s %r" % (secure and 'HTTPS' or 'HTTP', method, location,) 
        if self.requests_before_reconnect > 0:
            if self.requests_count > self.requests_before_reconnect:
                #open new connection
                self.requests_count = 1
                self.reset()
            self.requests_count += 1
        if secure:
            conn = self.https
        else:
            conn = self.http 
        print self.http
        if self.debug: print conn 
        if headers and 'Referrer' in headers:
            raise ValueError("Incorrect spelling - use referer not referrer") 
        # This strips out the :443 of https connections from the Host header by setting it manually.
        if not 'Host' in headers:
            headers['Host'] = self.site 
        try:
            try:
                conn.request( method, location, parameters, headers )
            except socket.error:
                conn.close()
                conn.request( method, location, parameters, headers )
            except httplib.CannotSendRequest:
                conn.close()
                conn.request( method, location, parameters, headers )
            try:
                resp = conn.getresponse()
            except httplib.BadStatusLine:
                conn.close()
                conn.request( method, location, parameters, headers )
                resp = conn.getresponse()
            except httplib.CannotSendRequest:
                conn.close()
                conn.request( method, location, parameters, headers )
                resp = conn.getresponse()
        except Exception, e:
            print "Reset browser.py %r because error %r" % (self, e,)
            self.reset()
            raise
        cookie = resp.getheader( 'set-cookie' )
        if cookie:
            self.cookies.add( cookie )
        protocol = 'http'
        if secure:
            protocol = 'https'
        self.last_visited = '%s://%s%s' % (protocol, self.site, location)
        # if this is a redirect:
        if resp.status >= 300 and resp.status < 400:
            # check if the site was specified and it differs from
            # the current one
            conn.close()
            location = resp.getheader('location')
            #print "redirecting to ", location
            parsed_location = urlparse.urlparse(location)
            http_or_https = protocol
            cls = LocalRedirect
            if parsed_location[1]:
                if parsed_location[1] != self.site:
                    cls = ExternalRedirect
                else:
                    # ignore the beginning bit
                    http_or_https = parsed_location[0]
                    parsed_location = list(parsed_location)
                    parsed_location[0] = ''
                    parsed_location[1] = ''
                    location = urlparse.urlunparse(parsed_location)
            # raise an exception for the redirection
            raise cls(location, resp.status, resp.reason, resp, http_or_https)
        # set the location that was visited, in case it differs from that which
        # was specified (i.e because of a redirect)
        resp.location = location
        return resp
    def set_cookie( self, string ):
        """ Adds a cookie """
        self.cookies.add( string )
    def clear_cookies( self ):
        """ Clears cookies """
        self.cookies = CookieJar()
    def reset( self ):
        """
        Close both connections and ensure that we are ready to go again.
        NOTE: This does NOT clear cookies
        """
        if self.http: self.http.close()
        self.http = httplib.HTTPConnection( self.site )
        if self.https: self.https.close()
        self.https  = httplib.HTTPSConnection( self.site )
        if self.debug:
            print 'Reset connection'
            if self.http:
                self.http.set_debuglevel(1)
            if self.https:
                self.https.set_debuglevel(1)


if __name__ == '__main__':
    import sys
    def test_site(name, quick=False):
        b = Browser( name, debug=False, guess_encoding=True )
        print '------ get ------------'
        r = b.get( '/' )
        text = r.read()
        print text
        print 'STATUS',r.status
        print 'REASON',r.reason
        if not quick:
            print '------ post ------------'
            r = b.post( '/', params="", raw=True )
            text2 = r.read()
            if text2 == text:
                print "(same as get)"
            else:
                print text
            print 'STATUS',r.status
            print 'REASON',r.reason
        if not quick:
            print '------ secure ------------'
            r = b.get( '/', secure=True )
            text2 = r.read()
            if text2 == text:
                print "(same as get)"
            else:
                print text
            print 'STATUS',r.status
            print 'REASON',r.reason
        print '------ get_page ------------'
        text2 = b.get_page("/")
        if text2 == text:
            print "(same as get)"
        else:
            print text
        print '------ done ------------'
    if '--test' in sys.argv:
        # UTF-8
        test_site('www.mozilla.org')
        # UTF-8
        test_site('www.mozilla.org.cn', quick=True)
        # EUC-JP
        test_site('www.mozilla-japan.org', quick=True)

