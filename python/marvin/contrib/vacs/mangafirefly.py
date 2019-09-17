# !usr/bin/env python
# -*- coding: utf-8 -*-
#
# Licensed under a 3-clause BSD license.
#
# @Author: Brian Cherinka
# @Date:   2018-10-11 17:51:43
# @Last modified by:   Brian Cherinka
# @Last Modified time: 2018-11-29 17:23:15

from __future__ import print_function, division, absolute_import

import numpy as np
import astropy
import marvin.tools
import matplotlib.pyplot as plt
from marvin import log
from .base import VACMixIn


class FIREFLYVAC(VACMixIn):
    """Provides access to the MaNGA-FIREFLY VAC.

    VAC name: FIREFLY

    URL: https://www.sdss.org/dr15/manga/manga-data/manga-firefly-value-added-catalog/

    Description: Returns integrated and resolved stellar population parameters fitted by FIREFLY

    Authors: Jianhui Lian, Daniel Thomas, Claudia Maraston, and Lewis Hill

    """

    # Required parameters
    name = 'firefly'
    description = 'Returns stellar population parameters fitted by FIREFLY'
    version = {'DR15': 'v1_1_2'}

    # optional Marvin Tools to attach your vac to
    include = (marvin.tools.cube.Cube, marvin.tools.maps.Maps, marvin.tools.modelcube.ModelCube)

    # Required method
    def get_data(self, parent_object):

        release = parent_object.release
        drpver = parent_object._drpver
        plateifu = parent_object.plateifu
        imagesz = int(parent_object.header['NAXIS1'])

        # define the variables to build a unique path to your VAC file
        path_params = {'ver': self.version[release], 'drpver': drpver}
        # get_path returns False if the files do not exist locally
        allfile = self.get_path('mangaffly', path_params=path_params)

        # download the vac from the SAS if it does not already exist locally
        if not allfile:
            log.info('Warning: This file is ~6 GB.  It may take awhile to download')
            allfile = self.download_vac('mangaffly', path_params=path_params)

        # create container for more complex return data.
        ffly = FFLY(plateifu, allfile=allfile, imagesz=imagesz)

        return ffly


class FFLY(object):
    def __init__(self, plateifu, allfile=None, imagesz=None):
        self._allfile = allfile
        self._plateifu = plateifu
        self._image_sz = imagesz
        self._ffly_data = self._open_file(allfile)
        self._indata = plateifu in self._ffly_data[1].data['plateifu']
        self._idx = self._ffly_data['GALAXY_INFO'].data['plateifu'] == self._plateifu
        self._parameters = ['lw_age', 'mw_age', 'lw_z', 'mw_z']

    @staticmethod
    def _open_file(fflyfile):
        return astropy.io.fits.open(fflyfile)

    def stellar_pops(self, parameter=None):
        ''' Returns the global stellar population properties

        Returns the global stellar population property within 1 Re for a given
        stellar population parameter.  If no parameter specified, returns the entire row.

        Parameters:
            parameter (str):
                The stellar population parameter to retrieve.  Can be one of ['lw_age', 'mw_age', 'lw_z', 'mw_z'].
        
        Returns:
            The data from the FIREFLY summary file for the target galaxy
        '''

        if parameter:
            assert parameter in self._parameters, 'parameter must be one of {0}'.format(
                self._parameters
            )

        if not self._indata:
            return "No FIREFLY result exists for {0}".format(self._plateifu)

        if parameter:
            return self._ffly_data['GLOBAL_PARAMETERS'].data[parameter + '_1re'][self._idx]
        else:
            return self._ffly_data['GLOBAL_PARAMETERS'].data[self._idx]

    def stellar_gradients(self, parameter=None):
        ''' Returns the gradient of stellar population properties

        Returns the gradient of the stellar population property for a given
        stellar population parameter.  If no parameter specified, returns the entire row.

        Parameters:
            parameter (str):
                The stellar population parameter to retrieve.  Can be one of ['lw_age', 'mw_age', 'lw_z', 'mw_z'].
        
        Returns:
            The data from the FIREFLY summary file for the target galaxy
        '''

        if parameter:
            assert parameter in self._parameters, 'parameter must be one of {0}'.format(
                self._parameters
            )

        if not self._indata:
            return "No FIREFLY result exists for {0}".format(self._plateifu)

        if parameter:
            return self._ffly_data['GRADIENT_PARAMETERS'].data[parameter + '_gradient'][self._idx]
        else:
            return self._ffly_data['GRADIENT_PARAMETERS'].data[self._idx]

    def _make_map(self, parameter=None):
        ''' Extract and create a 2d map '''

        params = self._parameters + [
            'e(b-v)',
            'stellar_mass',
            'surface_mass_density',
            'signal_noise',
        ]
        assert parameter in params, 'Parameter must be one of {0}'.format(params)

        # get the required arrays
        binid = self._ffly_data['SPATIAL_BINID'].data[self._idx].reshape(76, 76)
        bin1d = self._ffly_data['SPATIAL_INFO'].data[self._idx, :, 0][0]
        prop = self._ffly_data[parameter + '_voronoi'].data[self._idx, :, 0][0]
        image_sz = self._image_sz

        # make a base map and reshape to a 1d array
        maps = (np.zeros((image_sz, image_sz)) - 99).reshape(image_sz * image_sz)
        # find relevant elements in bin1d (anything not -9999)
        propinds = np.where(bin1d >= -1)
        # find relevant elements in binid (anything not -9999)
        inds = np.where(binid >= -1)
        # select the relevant elements from binid
        tmp = binid[inds]
        # find non-zero elements from the relevant elements
        newinds = np.where(tmp > -1)[0]
        # map the bin1d indices back to the original binid
        ai = bin1d[propinds].argsort()
        p = ai[np.searchsorted(bin1d[propinds], tmp[newinds], sorter=ai)]
        # replace map elements with the relevant prop parameter
        maps[newinds] = prop[p]
        # reshape the map array from 1d back to 2d
        maps = maps.reshape(image_sz, image_sz)

        return maps

    def plot_map(self, parameter=None, mask=None):
        ''' Plot map of stellar population properties
        
        Plots a 2d map of the specified FIREFLY stellar
        population parameter using Matplotlib.  Optionally mask
        the data when plotting using Numpy's Masked Array.  Default
        is to mask map values < -10. 

        Parameters:
            parameter (str):
                The named of the VORONOI stellar pop. parameter
            mask (nd-array):
                A Numpy array of masked values to apply to the map

        Returns:
            The matplotlib axis image object

        '''

        if not self._indata:
            return "No FIREFLY result exists for {0}".format(self._plateifu)

        # create the 2d map
        maps = self._make_map(parameter=parameter)

        # only show the spaxels with non-empty values
        mask = (maps < -10) if not mask else mask
        masked_array = np.ma.array(maps, mask=mask)

        # plot the masked map
        fig, ax = plt.subplots()
        axim = ax.imshow(masked_array, interpolation='nearest', cmap='RdYlBu_r', origin='lower')
        ax.set_xlabel('spaxel')
        ax.set_ylabel('spaxel')
        ax.set_title('Firefly {0}'.format(parameter.title()))

        # plot the colour bar
        cbar = fig.colorbar(axim, ax=ax, shrink=0.9)
        cbar.set_label(parameter.title(), fontsize=18, labelpad=20)
        cbar.ax.tick_params(labelsize=22)

        return axim
