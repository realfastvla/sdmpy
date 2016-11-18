#! /usr/bin/env python
import sys, math
import numpy as np
import logging
import sdmpy
import sdmpy.pulsar
import psrchive

import argparse
par = argparse.ArgumentParser(
        description="Convert phase-binned SDM/BDF data to fold-mode PSRFITS.")
par.add_argument("sdmname", help="SDM to process")
#par.add_argument("-v", "--verbose", dest='loglevel',
#        action='store_const', const=logging.DEBUG,
#        default=logging.INFO,
#        help='Enable DEBUG output')
par.add_argument("-q", "--quiet", dest='loglevel',
        action='store_const', const=logging.WARN,
        default=logging.INFO,
        help='No INFO messages')
par.add_argument("-d", "--dm", type=float, default=0.0,
        help="dispersion measure (pc cm^-3) [%(default)s]")
args = par.parse_args()

logging.basicConfig(format="%(asctime)-15s %(levelname)8s %(message)s", 
        level=args.loglevel)

sdmname = args.sdmname.rstrip('/')
sdm = sdmpy.SDM(sdmname)
try:
    binlog = sdmpy.pulsar.BinLog(sdmname)
except IOError:
    binlog = None

# TODO update to read 4-pol data
npol = 2

def unroll_chans(data):
    """Unroll the spw and channel dims into a single frequency axis.
    Assumes incoming dimensions are (bl, spw, bin, chan, pol)"""
    data = data.transpose((0,2,1,3,4))
    data = data.reshape((data.shape[0], 
        data.shape[1], 
        data.shape[2]*data.shape[3],
        data.shape[4]))
    return data

for scan in sdm.scans():
    if 'CALIBRATE_PHASE' in scan.intents:
        logging.info('processing cal scan %s' % scan.idx)
        # dims (bl,spw,bin,chan,pol)
        dcal = scan.bdf.get_data(scrunch=True)[...,[0,-1]].mean(2,
                keepdims=True)
        dcal = unroll_chans(dcal)
        gcal = sdmpy.calib.gaincal(dcal,axis=0,ref=1)
    elif 'OBSERVE_TARGET' in scan.intents:
        logging.info('processing target scan %s' % scan.idx)

        psr = str(scan.source)

        # Assumes all spws have same number of bins
        nbin = int(scan.bdf.spws[0].numBin)

        # Assumes all spws have same number of chans
        freqs = scan.freqs().ravel()/1e6
        chanidx = np.argsort(freqs)
        nchan = freqs.size
        bw = sum([scan.spw(i).totBandwidth/1e6 for i in range(len(scan.spws))])

        # Initialize archive output
        arch = psrchive.Archive_new_Archive("ASP")
        arch.resize(0,npol,nchan,nbin)
        arch.set_source(psr)
        arch.set_dispersion_measure(args.dm)
        arch.set_coordinates(psrchive.sky_coord(*scan.coordinates))
        arch.set_centre_frequency(0.5*(freqs.max() + freqs.min()))
        arch.set_bandwidth(bw)
        arch.set_telescope('vla')
        arch.set_state('PPQQ')

        iout = 0

        bdf = scan.bdf
        arch.resize(arch.get_nsubint() + bdf.numIntegration - 1)
        for isub in range(1,bdf.numIntegration):
            bdfsub = bdf[isub]
            dpsr = bdfsub.get_data()[...,[0,-1]]
            dpsr = unroll_chans(dpsr)
            sdmpy.calib.applycal(dpsr,gcal,phaseonly=True)
            dpsr = np.ma.masked_array(dpsr,dpsr==0.0)
            mpsr = np.real(dpsr.mean(0))
            subint = arch.get_Integration(iout)
            epoch_bdf = psrchive.MJD(float(bdfsub.time)) # only approx
            if binlog is not None:
                (epoch,p,dt) = binlog.epoch_period(epoch_bdf)
            else:
                (epoch,p,dt) = sdmpy.pulsar._get_epoch_period(epoch_bdf)

            logging.info('Using epoch/period from dt=%.3fs' % dt)

            # These were used for testing dedispersion:
            #sdmpy.pulsar._dedisperse_array(mpsr, args.dm, freqs, p,
            #        bin_axis=0,freq_axis=1)
            #sdmpy.pulsar._dedisperse_array(mpsr, args.dm, freqs_spw, p,
            #        bin_axis=2,freq_axis=3,spw_axis=1)
            #mpsr = unroll_chans(mpsr)[0,...]

            subint.set_epoch(epoch)
            subint.set_duration(bdfsub.interval)
            subint.set_folding_period(p)
            if isub==0:
                wt=0.0
            else:
                wt=1.0
            for ochan in range(nchan):
                ichan = chanidx[ochan]
                subint.set_centre_frequency(ochan,freqs[ichan])
                for ipol in range(npol):
                    prof = subint.get_Profile(ipol,ochan)
                    prof.get_amps()[:] = mpsr[:,ichan,ipol]
                subint.set_weight(ochan,wt)
            iout += 1

        outputname = sdmname + '.%03d.fits' % int(scan.idx)
        logging.info("unloading '%s'" % outputname)
        arch.unload(outputname)