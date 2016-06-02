#!/usr/bin/env python
# Copyright (c) 2016 IBM. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''
  Utilities to work with Spectrograms -- Power spectra v time (aka "waterfall" plots) 
'''

import numpy as np
from . import datareader


def complex_to_power(header, cdata, max_subband_bins_per_1khz_half_frame = 512):  
  '''
  header: header of raw data
  cdata: complex data

  '''
  
  # expose compamp measurement blocks
  cdata = cdata.reshape((header['number_of_half_frames'], header['number_of_subbands'], max_subband_bins_per_1khz_half_frame))  

  # FFT all blocks separately and rearrange output
  fftcdata = np.fft.fftshift(np.fft.fft(cdata), 2)  
  
  # slice out oversampled frequencies
  fftcdata = fftcdata[:, :, int(cdata.shape[2]*header['over_sampling']/2):-int(cdata.shape[2]*header['over_sampling']/2)] 

  # normalize and amplify by factor 15
  #TODO: why do we normalize? what are the units? 
  fftcdata = np.multiply(fftcdata.real**2 + fftcdata.imag**2, 15.0/cdata.shape[2])

  return fftcdata

def aca_reshape(arr):
  '''
  Assumes a 3D Numpy array, and reshapes like
  
  arr.reshape((arr.shape[0], arr.shape[1]*arr.shape[2]))

  This is useful for converting processed data from `complex_to_power`
  and from `autocorrelation` into a 2D array for image analysis and display.

  '''
  return arr.reshape((arr.shape[0], arr.shape[1]*arr.shape[2]))


def raw_to_spectrogram(raw_str, max_subband_bins_per_1khz_half_frame = 512):
  '''
  Extract both of these from the to_header_and_packed_data function.

  Returns spectrogram, with each row containing the measured power spectrum for a XX second time sample.

  Example: 
      import requests
      import ibmseti
      import matplotlib.pyplot as plt
      plt.ion()

      r = requests.get(aca_url)
 
      header, spectrogram = ibmseti.spectrograms.raw_to_spectrogram( r.content )

      fig, ax = plt.subplots()
      ax.imshow(spectrogram)
      
      #set the aspect ratio for visualization
      ax.set_aspect(float(spectrogram.shape[1]) / spectrogram.shape[0])

      #Time is on the horizontal axis and frequency bin is along the vertical.
  '''

  header, arr = datareader.to_header_and_packed_data(raw_str,
                                                     max_subband_bins_per_1khz_half_frame)

  power = complex_to_power(header, datareader.packed_data_to_complex(arr), 
                                        max_subband_bins_per_1khz_half_frame)
  
  return header, aca_reshape(power)

def scale_to_png(arr):
  return np.clip(arr * 255.0/arr.max() , 0, 255).astype(np.uint8)


def complex_to_ac(header, cdata, 
                  window=np.hanning,
                  max_subband_bins_per_1khz_half_frame=512):  # convert single or multi-subband compamps into autocorrelation waterfall

  '''
  Adapted from Gerry Harp at SETI.
  
  '''

  # expose compamp measurement blocks
  msbp1kzhf = max_subband_bins_per_1khz_half_frame
  cdata = cdata.reshape((header['number_of_half_frames'], header['number_of_subbands'], msbp1kzhf))  # expose compamp measurement blocks

  #Apply Windowing and Padding
  cdata = np.multiply(cdata, window(cdata.shape[2]))  # window for smoothing sharp time series start/end in freq. dom.
  cdata_normal = cdata - cdata.mean(axis=2)[:, :, np.newaxis]  # zero mean, does influence a minority of lines in some plots

  cdata = np.zeros((cdata.shape[0], cdata.shape[1], 2 * cdata.shape[2]), complex)
  cdata[:, :, cdata.shape[2]/2:cdata.shape[2] + cdata.shape[2]/2] = cdata_normal  # zero-pad to 2N

  #Perform Autocorrelation
  cdata = np.fft.fftshift(np.fft.fft(cdata), 2)  # FFT all blocks separately and arrange correctly
  cdata = cdata.real**2 + cdata.imag**2  # FFT(AC(x)) = FFT(x)FFT*(x) = abs(x)^2
  cdata = np.fft.ifftshift(np.fft.ifft(cdata), 2)  # AC(x) = iFFT(abs(x)^2) and arrange correctly
  cdata = np.abs(cdata)  # magnitude of AC

  # normalize each row to sqrt of AC triangle
  cdata = np.divide(cdata, np.sqrt(np.sum(cdata, axis=2))[:, :, np.newaxis])  

  return cdata

def ac_viz(acdata):
  '''
  Adapted from Gerry Harp at SETI.
  
  Slightly massages the autocorrelated calculation result for better visualization.

  In particular, the natural log of the data are calculated and the
  values along the subband edges are set to the maximum value of the data, 
  and the t=0 delay of the autocorrelation result are set to the value of the t=-1 delay.

  This is allowed because the t=0, and subband edges do not carry any information. 

  To avoid log(0), a value of 0.000001 is added to all array elements before being logged. 
  '''

  acdata = np.log(acdata+0.000001)  # log to reduce darkening on sides of spectrum, due to AC triangling
  acdata[:, :, acdata.shape[2]/2] = acdata[:, :, acdata.shape[2]/2 - 1]  # vals at zero delay set to symmetric neighbor vals
  acdata[:, :, acdata.shape[2] - 1] = np.max(acdata)  # visualize subband edges

  return acdata

def raw_to_ac(raw_str, window = np.hanning, max_subband_bins_per_1khz_half_frame = 512):

  header, packed_data = datareader.to_header_and_packed_data(raw_str, max_subband_bins_per_1khz_half_frame)
  cdata = datareader.packed_data_to_complex(packed_data)

  acdata = complex_to_ac(header, cdata, window, max_subband_bins_per_1khz_half_frame)
  
  return header, acdata


