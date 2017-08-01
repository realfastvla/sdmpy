import sdmpy
import numpy as np
import xarray


def read(sdmfile, sdmscan):
    """ Read scan from sdm and return xarray version of visibility data.
    """

    sdm = sdmpy.SDM(path=sdmfile, use_xsd=False)
    scan = sdm.scan(sdmscan)
    bdf = scan.bdf

    inttime = bdf.get_integration(0).interval
    starttime_mjd = bdf.startTime
    stoptime_mjd = starttime_mjd + (bdf.numIntegration*inttime)/(24*3600)
    times = np.linspace(starttime_mjd, stoptime_mjd, num=bdf.numIntegration)

    baselines = ['{0}-{1}'.format(scan.antennas[i], scan.antennas[j])
                 for j in range(bdf.numAntenna)
                 for i in range(0, j)]

    spws = scan.reffreqs
    bins = [0]  # **hack**
    channels = np.linspace(0, scan.chanwidths[0]*scan.numchans[0],
                           scan.numchans[0])

    spw = bdf.spws[0]
    polarizations = spw._attrib['crossPolProducts'].split(' ')  # **hack**

    xarr = xarray.DataArray(bdf.get_data(),
                            dims=['time', 'baseline', 'spw', 'bin', 'channel',
                                  'polarization'],
                            coords=[times, baselines, spws, bins, channels,
                                    polarizations])

    return xarr
