# Licensed under a 3-clause BSD style license
"""
Marvin is a package intended to simply the access, exploration, and visualization of
the MaNGA dataset for SDSS-IV.  It provides a suite of Python tools, a web interface,
and a REST-like API, under tools/, web/, and api/, respectively.  Core functionality
of Marvin stems from Marvin's Brain.
"""

import os
import re
import warnings
import sys
import contextlib
import marvin
from collections import OrderedDict

# Set the Marvin version
__version__ = '2.2.3'
# try:
#     from marvin.version import get_version
# except ImportError as e:
#     __version__ = 'dev'
# else:
#     __version__ = get_version()

# Does this so that the implicit module definitions in extern can happen.
from marvin import extern

from marvin.core.exceptions import MarvinUserWarning, MarvinError
from brain.utils.general.general import getDbMachine
from brain import bconfig
from brain.core.core import URLMapDict
from brain.core.exceptions import BrainError

# Inits the log
from brain.core.logger import initLog

from astropy.wcs import FITSFixedWarning

# Defines log dir.
if 'MARVIN_LOGS_DIR' in os.environ:
    logFilePath = os.path.join(os.path.realpath(os.environ['MARVIN_LOGS_DIR']), 'marvin.log')
else:
    logFilePath = os.path.realpath(os.path.join(os.environ['HOME'], '.marvin', 'marvin.log'))

log = initLog(logFilePath)

warnings.simplefilter('once')
warnings.filterwarnings('ignore', 'Skipped unsupported reflection of expression-based index')
warnings.filterwarnings('ignore', '(.)+size changed, may indicate binary incompatibility(.)+')
warnings.filterwarnings('ignore', category=FITSFixedWarning)

# Filters for PY3
# TODO: undestand why these warnings are issued and fix the root of the problem (JSG)
warnings.filterwarnings('ignore', 'can\'t resolve package(.)+')
warnings.filterwarnings('ignore', 'unclosed file <_io.TextIOWrapper+')


class MarvinConfig(object):
    ''' Global Marvin Configuration

    The global configuration of Marvin.  Use the config object to globally set options for
    your Marvin session.

    Parameters:
        release (str):
            The release version of the MaNGA data you want to use.  Either MPL or DR.
        download (bool):
            Set to turn on downloading of objects with sdss_access
        use_sentry (bool):
            Set to turn on/off the Sentry error logging.  Default is True.
        add_github_message (bool):
            Set to turn on/off the additional Github Issue message in MarvinErrors. Default is True.
        drpall (str):
            The location to your DRPall file, based on which release you have set.
        mode (str):
            The current mode of Marvin.  Either 'auto', 'remote', or 'local'. Default is 'auto'
        sasurl (str):
            The url of the Marvin API on the Utah Science Archive Server (SAS)
        urlmap (dict):
            A dictionary containing the API routing information used by Marvin
        xyorig (str):
            Globally set the origin point for all your spaxel selections.  Either 'center' or 'lower'.
            Default is 'center'
    '''
    def __init__(self):

        self._drpall = None
        self._inapp = False

        self._urlmap = None
        self._xyorig = None

        self._release = None

        self.vermode = None
        self.download = False
        self.use_sentry = True
        self.add_github_message = True
        self._allowed_releases = {}

        # perform some checks
        self._check_netrc()
        self._check_config()
        self._setDbConfig()

        # setup some paths
        self._plantTree()
        self._checkSDSSAccess()
        self._check_manga_dirs()
        self.setDefaultDrpAll()

    def _checkPaths(self, name):
        ''' Check for the necessary path existence.

            This should only run if someone already has TREE_DIR installed
            but somehow does not have a SAS_BASE_DIR, MANGA_SPECTRO_REDUX, or
            MANGA_SPECTRO_ANALYSIS directory
        '''

        # set the access work path
        workpath = 'mangawork' if self.access == 'collab' else self.release.lower()

        name = name.upper()
        if name not in os.environ:
            if name == 'SAS_BASE_DIR':
                path_dir = os.path.expanduser('~/sas')
            elif name == 'MANGA_SPECTRO_REDUX':
                path_dir = os.path.join(os.path.abspath(os.environ['SAS_BASE_DIR']), '{0}/manga/spectro/redux'.format(workpath))
            elif name == 'MANGA_SPECTRO_ANALYSIS':
                path_dir = os.path.join(os.path.abspath(os.environ['SAS_BASE_DIR']), '{0}/manga/spectro/analysis'.format(workpath))

            if not os.path.exists(path_dir):
                warnings.warn('no {0}_DIR found. Creating it in {1}'.format(name, path_dir))
                os.makedirs(path_dir)
            os.environ[name] = path_dir

    @staticmethod
    def set_custom_path(name, path):
        ''' Set a temporary custom environment variable path

        Custom define a new environment variable in the current
        os session.  Puts it in your os.environ.  To permanently
        set a custom variable, use your .bashrc or .cshrc file.

        Parameters:
            name (str):
                The name of the environment variable
            path (str):
                The file path
        '''
        name = name.upper()
        os.environ[name] = path

    def _check_netrc(self):
        """Makes sure there is a valid netrc."""

        try:
            valid_netrc = bconfig._check_netrc()
        except BrainError as e:
            pass
        else:
            # if it's valid, then auto set to collaboration
            if valid_netrc:
                self.access = 'collab'

    def _check_manga_dirs(self):
        """Check if $SAS_BASE_DIR and MANGA dirs are defined.
           If they are not, creates and defines them.
        """

        self._checkPaths('SAS_BASE_DIR')
        self._checkPaths('MANGA_SPECTRO_REDUX')
        self._checkPaths('MANGA_SPECTRO_ANALYSIS')

    def setDefaultDrpAll(self, drpver=None):
        """Tries to set the default location of drpall.

        Sets the drpall attribute to the location of your DRPall file, based on the
        drpver.  If drpver not set, it is extracted from the release attribute.  It sets the
        location based on the MANGA_SPECTRO_REDUX environment variable

        Parameters:
            drpver (str):
                The DRP version to set.  Defaults to the version corresponding to config.release.
        """

        if not drpver:
            drpver, __ = self.lookUpVersions(self.release)
        self.drpall = self._getDrpAllPath(drpver)

    def _getDrpAllPath(self, drpver):
        """Returns the default path for drpall, give a certain ``drpver``."""

        if 'MANGA_SPECTRO_REDUX' in os.environ and drpver:
            return os.path.join(os.environ['MANGA_SPECTRO_REDUX'], str(drpver),
                                'drpall-{0}.fits'.format(drpver))
        else:
            raise MarvinError('Must have the MANGA_SPECTRO_REDUX environment variable set')

############ Brain Config overrides ############
# These are configuration parameter defined in Brain.bconfig. We need
# to be able to modify them during run time, so we define properties and
# setters to do that from Marvin.config.

    @property
    def mode(self):
        return bconfig.mode

    @mode.setter
    def mode(self, value):
        bconfig.mode = value

    @property
    def sasurl(self):
        return bconfig.sasurl

    @sasurl.setter
    def sasurl(self, value):
        bconfig.sasurl = value

    @property
    def release(self):
        return self._release

    @release.setter
    def release(self, value):
        value = value.upper()
        if value not in self._allowed_releases:
            raise MarvinError('trying to set an invalid release version. Valid releases are: {0}'
                              .format(', '.join(self._allowed_releases)))

        # set the new release and possibly replant the tree
        with self._replant_tree(value) as val:
            self._release = val

        drpver, __ = self.lookUpVersions(value)
        self.drpall = self._getDrpAllPath(drpver)

    @property
    def access(self):
        return bconfig.access

    @access.setter
    def access(self, value):
        bconfig.access = value

        # update and recheck the releases
        self._check_config()

    @property
    def session_id(self):
        return bconfig.session_id

    @session_id.setter
    def session_id(self, value):
        bconfig.session_id = value

    @property
    def _traceback(self):
        return bconfig.traceback

    @_traceback.setter
    def _traceback(self, value):
        bconfig.traceback = value

#################################################

    @property
    def urlmap(self):
        """Retrieves the URLMap the first time it is needed."""

        if self._urlmap is None or (isinstance(self._urlmap, dict) and len(self._urlmap) == 0):
            try:
                response = Interaction('api/general/getroutemap', request_type='get')
            except Exception as e:
                warnings.warn('Cannot retrieve URLMap. Remote functionality will not work: {0}'.format(e),
                              MarvinUserWarning)
                self.urlmap = URLMapDict()
            else:
                self.urlmap = response.getRouteMap()

        return self._urlmap

    @urlmap.setter
    def urlmap(self, value):
        """Manually sets the URLMap."""
        self._urlmap = value
        arg_validate.urlmap = self._urlmap

    @property
    def xyorig(self):
        if not self._xyorig:
            self._xyorig = 'center'

        return self._xyorig

    @xyorig.setter
    def xyorig(self, value):

        assert value.lower() in ['center', 'lower'], 'xyorig must be center or lower.'

        self._xyorig = value.lower()

    @property
    def drpall(self):
        return self._drpall

    @drpall.setter
    def drpall(self, value):
        if os.path.exists(value):
            self._drpall = value
        else:
            self._drpall = None
            warnings.warn('path {0} cannot be found. Setting drpall to None.'
                          .format(value), MarvinUserWarning)

    def _setDbConfig(self):
        ''' Set the db configuration '''
        self.db = getDbMachine()

    def _update_releases(self):
        ''' Update the allowed releases based on access '''

        # define release dictionaries
        mpldict = {'MPL-6': ('v2_3_1', '2.1.3'),
                   'MPL-5': ('v2_0_1', '2.0.2'),
                   'MPL-4': ('v1_5_1', '1.1.1')}

        drdict = {'DR15': ('v2_4_0', '2.2.0'),
                  'DR14': ('v2_2_0', '2.1.0')}

        # set the allowed releases based on access
        self._allowed_releases = {}
        if self.access == 'public':
            self._allowed_releases.update(drdict)
        elif self.access == 'collab':
            self._allowed_releases.update(drdict)
            self._allowed_releases.update(mpldict)

        # create and sort the final OrderedDict
        relsorted = sorted(self._allowed_releases.items(), key=lambda p: p[1][0], reverse=True)
        self._allowed_releases = OrderedDict(relsorted)

    def _get_latest_release(self, mpl_only=None):
        ''' Get the latest release from allowed list '''

        if mpl_only:
            return [r for r in list(self._allowed_releases) if 'MPL' in r][0]

        return list(self._allowed_releases)[0]

    def _check_config(self):
        ''' Check the release in the config '''

        # update the allowed releases
        self._update_releases()

        # Check for release version and if in allowed list
        latest = self._get_latest_release(mpl_only=self.access == 'collab')
        if not self.release:
            log.info('No release version set. Setting default to {0}'.format(latest))
            self.setRelease(latest)
        elif self.release and self.release not in self._allowed_releases:
            # this toggles to latest DR when switching to public
            warnings.warn('Release {0} is not in the allowed releases.  '
                          'Switching to {1}'.format(self.release, latest), MarvinUserWarning)
            self.setRelease(latest)

    def setRelease(self, version=None):
        """Set the release version.

        Parameters:
            version (str):
                The MPL/DR version to set, in form of MPL-X or DRXX.

        Example:
            >>> config.setRelease('MPL-4')
            >>> config.setRelease('DR13')

        """

        # if no version is set, pull the latest one by default
        if not version:
            version = self._get_latest_release()

        version = version.upper()
        self.release = version

    def setMPL(self, mplver):
        """As :func:`setRelease` but check that the version is an MPL."""

        self.setRelease(mplver)

    def setDR(self, drver):
        """As :func:`setRelease` but check that the version is a DR."""

        self.setRelease(drver)

    def lookUpVersions(self, release=None):
        """Retrieve the DRP and DAP versions that make up a release version.

        Parameters:
            release (str or None):
                The release version. If ``None``, uses the currently set
                ``release`` value.

        Returns:
            drpver, dapver (tuple):
                A tuple of strings of the DRP and DAP versions according
                to the input MPL version

        """

        release = release or self.release

        try:
            drpver, dapver = self._allowed_releases[release]
        except KeyError:
            raise MarvinError('MPL/DR version {0} not found in lookup table. '
                              'No associated DRP/DAP versions. '
                              'Should they be added?  Check for typos.'.format(release))

        return drpver, dapver

    def lookUpRelease(self, drpver):
        """Retrieve the release version for a given DRP version

        Parameters:
            drpver (str):
                The DRP version to use
        Returns:
            release (str):
                The release version according to the input DRP version
        """

        # Flip the mpldict
        verdict = {val[0]: key for key, val in self._allowed_releases.items()}

        try:
            release = verdict[drpver]
        except KeyError:
            raise MarvinError('DRP version {0} not found in lookup table. '
                              'No associated MPL version. Should one be added?  '
                              'Check for typos.'.format(drpver))

        return release

    def switchSasUrl(self, sasmode='utah', ngrokid=None, port=5000, test=False):
        ''' Switches the SAS url config attribute

        Easily switch the sasurl configuration variable between
        utah and local.  utah sets it to the real API.  Local switches to
        use localhost.

        Parameters:
            sasmode ({'utah', 'local'}):
                the SAS mode to switch to.  Default is Utah
            ngrokid (str):
                The ngrok id to use when using a 'localhost' sas mode.
                This assumes localhost server is being broadcast by ngrok
            port (int):
                The port of your localhost server
            test (bool):
                If ``True``, sets the Utah sasurl to the test production, test/marvin2
        '''
        assert sasmode in ['utah', 'local'], 'SAS mode can only be utah or local'
        if sasmode == 'local':
            if ngrokid:
                self.sasurl = 'http://{0}.ngrok.io/marvin2/'.format(ngrokid)
            else:
                self.sasurl = 'http://localhost:{0}/marvin2/'.format(port)
        elif sasmode == 'utah':
            marvin_base = 'test/marvin2/' if test else 'marvin2/'
            self.sasurl = 'https://api.sdss.org/{0}'.format(marvin_base)
        self.urlmap = None

    def forceDbOff(self):
        ''' Force the database to be turned off '''
        config.db = None
        from marvin import marvindb
        marvindb.forceDbOff()

    def forceDbOn(self):
        ''' Force the database to be reconnected '''
        self._setDbConfig()
        from marvin import marvindb
        marvindb.forceDbOn(dbtype=self.db)

    def _addExternal(self, name):
        ''' Adds an external product into the path '''
        assert isinstance(name, str), 'name must be a string'
        externdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'extern', name)
        extern_envvar = '{0}_DIR'.format(name.upper())
        os.environ[extern_envvar] = externdir
        pypath = os.path.join(externdir, 'python')
        if os.path.isdir(pypath):
            sys.path.append(pypath)
        else:
            warnings.warn('Python path for external product {0} does not exist'.format(name))

    def _plantTree(self):
        ''' Sets up the sdss tree product root '''

        tree_config = 'sdsswork' if self.access == 'collab' and 'MPL' in self.release else self.release.lower()

        # testing always using the python Tree as override
        # if 'TREE_DIR' not in os.environ:
        # set up tree using marvin's extern package
        self._addExternal('tree')
        try:
            from tree.tree import Tree
        except ImportError:
            self._tree = None
        else:
            self._tree = Tree(key='MANGA', config=tree_config)

    def _checkSDSSAccess(self):
        ''' Checks the client sdss_access setup '''
        if 'SDSS_ACCESS_DIR' not in os.environ:
            # set up sdss_access using marvin's extern package
            self._addExternal('sdss_access')
            try:
                from sdss_access.path import Path
            except ImportError:
                Path = None
            else:
                self._sdss_access_isloaded = True

    @contextlib.contextmanager
    def _replant_tree(self, value):
        ''' Replants the tree based on release/access toggling

        Context manager for use when setting a new release

        Parameters:
            value (str):
                A new release
        '''

        # switch between public and collab access
        if hasattr(self, '_tree'):
            tocollab = self.access == 'collab' and self._tree.config_name != 'sdsswork'
            topublic = self.access == 'public' and self._tree.config_name == 'sdsswork'

        # switch trees based on release

        # check if release is different
        is_different = self._release and value != self._release

        # remove and return similar characters from value in self._release
        if self._release:
            similar = re.sub('[^{0}]'.format(self._release.replace('-', '\-')), '', value)
            stilldr = 'DR' in similar
            stillmpl = 'MPL' in similar
            relchange = stilldr is False and stillmpl is False

        # yield the value (a release)
        yield value

        # set tree_config
        tree_config = 'sdsswork' if 'MPL' in value else value.lower() if 'DR' in value else None

        # replant the tree
        if is_different:
            if (relchange and self.access == 'collab') or stilldr or topublic or tocollab:
                self._tree.replant_tree(tree_config)

config = MarvinConfig()

# Inits the Database session and ModelClasses
from marvin.db.marvindb import MarvinDB
marvindb = MarvinDB(dbtype=config.db)

# Init MARVIN_DIR
marvindir = os.environ.get('MARVIN_DIR', None)
if not marvindir:
    moduledir = os.path.dirname(os.path.abspath(__file__))
    marvindir = moduledir.rsplit('/', 2)[0]
    os.environ['MARVIN_DIR'] = marvindir

# Inits the URL Route Map
from marvin.api.api import Interaction
config.sasurl = 'https://api.sdss.org/marvin2/'

from marvin.api.base import arg_validate
