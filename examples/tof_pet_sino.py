# small demo for sinogram TOF OS-MLEM

import os
import matplotlib.pyplot as plt
import pyparallelproj as ppp
from pyparallelproj.algorithms import osem, spdhg

import numpy as np
from scipy.ndimage import gaussian_filter

from phantoms import ellipse_phantom
from pymirc.image_operations import grad, div

import argparse

#---------------------------------------------------------------------------------
# parse the command line

parser = argparse.ArgumentParser()
parser.add_argument('--ngpus',    help = 'number of GPUs to use', default = 0,   type = int)
parser.add_argument('--counts',   help = 'counts to simulate',    default = 1e5, type = float)
parser.add_argument('--niter',    help = 'number of iterations',  default = 50,  type = int)
parser.add_argument('--niter_ref', help = 'number of ref iterations', default = 20000,  type = int)
parser.add_argument('--nsubsets',   help = 'number of subsets',     default = 28,  type = int)
parser.add_argument('--warm'  ,   help = 'warm start with 1 OSEM it', action = 'store_true')
parser.add_argument('--interactive', help = 'show recons updates', action = 'store_true')
parser.add_argument('--fwhm_mm',  help = 'psf modeling FWHM mm',  default = 4.5, type = float)
parser.add_argument('--fwhm_data_mm',  help = 'psf for data FWHM mm',  default = 4.5, type = float)
parser.add_argument('--phantom', help = 'phantom to use', default = 'brain2d')
parser.add_argument('--seed',    help = 'seed for random generator', default = 1, type = int)
parser.add_argument('--beta',   help = 'beta for TV', default = 1e-3, type = float)
args = parser.parse_args()

#---------------------------------------------------------------------------------

ngpus         = args.ngpus
counts        = args.counts
niter         = args.niter
niter_ref     = args.niter_ref
nsubsets      = args.nsubsets
fwhm_mm       = args.fwhm_mm
fwhm_data_mm  = args.fwhm_data_mm
warm          = args.warm
interactive   = args.interactive
phantom       = args.phantom
seed          = args.seed
ps_fwhm_mm    = 8.
beta          = args.beta

gammas = np.array([0.3,1,3,10,30]) / (counts/1e3)

it_early = 20
#---------------------------------------------------------------------------------

np.random.seed(seed)

# setup a scanner with one ring
scanner = ppp.RegularPolygonPETScanner(ncrystals_per_module = np.array([16,1]),
                                       nmodules             = np.array([28,1]))

# setup a test image
voxsize = np.array([2.,2.,2.])
n2      = max(1,int((scanner.xc2.max() - scanner.xc2.min()) / voxsize[2]))

# sigma for post_smoothing
sig     = ps_fwhm_mm / (voxsize*2.35)

# convert fwhm from mm to pixels
fwhm      = fwhm_mm / voxsize
fwhm_data = fwhm_data_mm / voxsize

# setup a random image

if phantom == 'ellipse':
  n   = 200
  img = np.zeros((n,n,n2), dtype = np.float32)
  for i2 in range(n2):
    img[:,:,i2] = ellipse_phantom(n = n, c = 3)
elif phantom == 'brain2d':
  n   = 128
  img = np.zeros((n,n,n2), dtype = np.float32)
  tmp = np.load(os.path.join('data','brain2d.npy'))
  for i2 in range(n2):
    img[:,:,i2] = tmp

img_origin = (-(np.array(img.shape) / 2) +  0.5) * voxsize

# setup an attenuation image
att_img = (img > 0) * 0.01 * voxsize[0]

# generate nonTOF sinogram parameters and the nonTOF projector for attenuation projection
sino_params_nt = ppp.PETSinogramParameters(scanner)
proj_nt        = ppp.SinogramProjector(scanner, sino_params_nt, img.shape, nsubsets = 1, 
                                    voxsize = voxsize, img_origin = img_origin, ngpus = ngpus)

attn_sino = np.exp(-proj_nt.fwd_project(att_img))

# generate the sensitivity sinogram
sens_sino = np.ones(sino_params_nt.shape, dtype = np.float32)

# generate TOF sinogram parameters and the TOF projector
sino_params = ppp.PETSinogramParameters(scanner, ntofbins = 17, tofbin_width = 15.)
proj        = ppp.SinogramProjector(scanner, sino_params, img.shape, nsubsets = 1, 
                                    voxsize = voxsize, img_origin = img_origin, ngpus = ngpus,
                                    tof = True, sigma_tof = 60./2.35, n_sigmas = 3.)

# estimate the norm of the operator
test_img = np.random.rand(*img.shape)
for i in range(10):
  fwd  = ppp.pet_fwd_model(test_img, proj, attn_sino, sens_sino, 0, fwhm = fwhm)
  back = ppp.pet_back_model(fwd, proj, attn_sino, sens_sino, 0, fwhm = fwhm)

  norm = np.linalg.norm(back)
  print(i,norm)

  test_img = back / norm

# normalize sensitivity sinogram to get PET forward model with norm 1
sens_sino /= np.sqrt(norm)

# forward project the image
img_fwd= ppp.pet_fwd_model(img, proj, attn_sino, sens_sino, 0, fwhm = fwhm_data)

# scale sum of fwd image to counts
if counts > 0:
  scale_fac = (counts / img_fwd.sum())
  img_fwd  *= scale_fac 
  img      *= scale_fac 

  # contamination sinogram with scatter and randoms
  # useful to avoid division by 0 in the ratio of data and exprected data
  contam_sino = np.full(img_fwd.shape, 0.2*img_fwd.mean(), dtype = np.float32)
  
  em_sino = np.random.poisson(img_fwd + contam_sino)
else:
  scale_fac = 1.

  # contamination sinogram with sctter and randoms
  # useful to avoid division by 0 in the ratio of data and exprected data
  contam_sino = np.full(img_fwd.shape, 0.2*img_fwd.mean(), dtype = np.float32)

  em_sino = img_fwd + contam_sino

#-------------------------------------------------------------------------------------
#-------------------------------------------------------------------------------------

if interactive:
  fig, ax = plt.subplots(1,3, figsize = (12,4))
  ax[0].imshow(img[...,n2//2],   vmin = 0, vmax = 1.3*img.max(), cmap = plt.cm.Greys)
  ax[0].set_title('ground truth')
  ir = ax[1].imshow(0*img[...,n2//2], vmin = 0, vmax = 1.3*img.max(), cmap = plt.cm.Greys)
  ax[1].set_title('recon')
  ib = ax[2].imshow(img[...,n2//2] - img[...,n2//2], vmin = -0.2*img.max(), vmax = 0.2*img.max(), 
                    cmap = plt.cm.bwr)
  ax[2].set_title('bias')
  fig.tight_layout()
  plt.pause(1e-6)


#-----------------------------------------------------------------------------------------------
# callback functions to calculate likelihood and show recon updates

def update_img(x):
  ir.set_data(x[...,n2//2])
  ib.set_data(x[...,n2//2] - img[...,n2//2])
  plt.pause(1e-6)

def calc_cost(x):
  cost = 0

  for i in range(proj.nsubsets):
    # get the slice for the current subset
    ss = proj.subset_slices[i]
    exp = ppp.pet_fwd_model(x, proj, attn_sino[ss], sens_sino[ss], i, fwhm = fwhm) + contam_sino[ss]
    cost += (exp - em_sino[ss]*np.log(exp)).sum()

  if beta > 0:
    x_grad = np.zeros((img.ndim,) + img.shape, dtype = np.float32)
    grad(x, x_grad)
    cost += beta*np.linalg.norm(x_grad, axis = 0).sum()

  return cost

def _cb(x, **kwargs):
  it = kwargs.get('iteration',0)
  it_early = kwargs.get('it_early',-1)

  if it_early == it:
    if 'x_early' in kwargs:
      kwargs['x_early'][:] = x

  if interactive: 
    update_img(x)
  if 'cost' in kwargs:
    kwargs['cost'][it-1] = calc_cost(x)
  if 'psnr' in kwargs:
    MSE = ((x - kwargs['xref'])**2).mean()
    kwargs['psnr'][it-1] = 20*np.log10(kwargs['xref'].max()/np.sqrt(MSE))
  if 'psnr_ps' in kwargs:
    x_ps = gaussian_filter(x, kwargs['sig'])
    MSE = ((x_ps - kwargs['xref_ps'])**2).mean()
    kwargs['psnr_ps'][it-1] = 20*np.log10(kwargs['xref_ps'].max()/np.sqrt(MSE))

#-----------------------------------------------------------------------------------------------

# do long MLEM as reference
if beta > 0:
  ref_fname = os.path.join('data', f'PDHG_{phantom}_TVbeta_{beta:.1E}_niter_{niter_ref}_counts_{counts:.1E}_seed_{seed}.npz')
else:
  ref_fname = os.path.join('data', f'mlem_{phantom}_niter_{niter_ref}_counts_{counts:.1E}_seed_{seed}.npz')

if os.path.exists(ref_fname):
  tmp = np.load(ref_fname)
  ref_recon = tmp['ref_recon']
  ref_cost  = tmp['ref_cost']
else:
  ref_cost  = np.zeros(niter_ref)

  if beta > 0:
    ref_recon = spdhg(em_sino, attn_sino, sens_sino, contam_sino, proj, niter_ref,
                      gamma = 3./(counts/1e3), fwhm = fwhm, verbose = True, 
                      beta = beta, callback = _cb, callback_kwargs = {'cost': ref_cost})
  else:
    ref_recon = osem(em_sino, attn_sino, sens_sino, contam_sino, proj, niter_ref,
                     fwhm = fwhm, verbose = True, callback = _cb, callback_kwargs = {'cost': ref_cost})

  np.savez(ref_fname, ref_recon = ref_recon, ref_cost = ref_cost)

ref_recon_ps = gaussian_filter(ref_recon, sig)

# initialize the subsets for the projector
proj.init_subsets(nsubsets)

if warm:
  init_recon = osem(em_sino, attn_sino, sens_sino, contam_sino, proj, 1, 
                    fwhm = fwhm, verbose = True)
else:
  init_recon = None

cost_osem    = np.zeros(niter)
psnr_osem    = np.zeros(niter)
psnr_ps_osem = np.zeros(niter)

recon_osem_early = np.zeros(tuple(proj.img_dim), dtype = np.float32)

if beta == 0:
  cbk = {'cost':cost_osem, 'xref':ref_recon, 'psnr':psnr_osem, 
         'xref_ps':ref_recon_ps, 'psnr_ps':psnr_ps_osem, 'sig':sig,
         'it_early':it_early, 'x_early': recon_osem_early}
  recon_osem = osem(em_sino, attn_sino, sens_sino, contam_sino, proj, niter, 
                    fwhm = fwhm, verbose = True, xstart = init_recon,
                    callback = _cb, callback_kwargs = cbk)

ystart = np.zeros(em_sino.shape, dtype = np.float32)
ystart[em_sino == 0] = 1

costs_spdhg = np.zeros((len(gammas),niter))
costs_spdhg_sparse = np.zeros((len(gammas),niter))

psnr_spdhg = np.zeros((len(gammas),niter))
psnr_spdhg_sparse = np.zeros((len(gammas),niter))
psnr_ps_spdhg = np.zeros((len(gammas),niter))
psnr_ps_spdhg_sparse = np.zeros((len(gammas),niter))

recons_spdhg        = np.zeros((len(gammas),) + img.shape, dtype = np.float32)
recons_spdhg_sparse = np.zeros((len(gammas),) + img.shape, dtype = np.float32)

recons_spdhg_early        = np.zeros((len(gammas),) + img.shape, dtype = np.float32)
recons_spdhg_sparse_early = np.zeros((len(gammas),) + img.shape, dtype = np.float32)

for ig, gamma in enumerate(gammas):
  cbs = {'cost':costs_spdhg[ig,:], 'xref':ref_recon, 'psnr':psnr_spdhg[ig,:],
         'xref_ps':ref_recon_ps, 'psnr_ps':psnr_ps_spdhg[ig,:], 'sig':sig,
         'it_early':it_early, 'x_early': recons_spdhg_early[ig,...]}

  recons_spdhg[ig,...] = spdhg(em_sino, attn_sino, sens_sino, contam_sino, proj, niter,
                               gamma = gamma, fwhm = fwhm, verbose = True, 
                               xstart = init_recon, beta = beta,
                               callback = _cb, callback_kwargs = cbs)

  cbss = {'cost':costs_spdhg_sparse[ig,:], 'xref':ref_recon, 'psnr':psnr_spdhg_sparse[ig,:],
          'xref_ps':ref_recon_ps, 'psnr_ps':psnr_ps_spdhg_sparse[ig,:], 'sig':sig,
          'it_early':it_early, 'x_early': recons_spdhg_sparse_early[ig,...]}
  recons_spdhg_sparse[ig,...] = spdhg(em_sino, attn_sino, sens_sino, contam_sino, proj, niter,
                                      gamma = gamma, fwhm = fwhm, verbose = True,
                                      xstart = init_recon, ystart = ystart, beta = beta,
                                      callback = _cb, callback_kwargs = cbss)

# show the cost and PSNR
it = np.arange(niter) + 1
base_str = f'{phantom}_counts_{counts:.1E}_beta_{beta:.1E}_niter_{niter_ref}_{niter}_nsub_{nsubsets}'

if  beta== 0:
  fig2, ax2 = plt.subplots(3, len(gammas), figsize = (len(gammas)*2,6), 
                           sharex = True, sharey = 'row')
else:
  fig2, ax2 = plt.subplots(2, len(gammas), figsize = (len(gammas)*2,4), 
                           sharex = True, sharey = 'row')

for ig, gamma in enumerate(gammas):
  if beta == 0:
    ax2[0,ig].plot(it,cost_osem, label = 'OSEM')
  ax2[0,ig].plot(it,costs_spdhg[ig,:], label = f'SPDHG')
  ax2[0,ig].plot(it,costs_spdhg_sparse[ig,:], label = f'SPDHG-S')
  ax2[0,ig].set_title(f'Gamma {gamma:.1E}', fontsize = 'medium')

  if beta == 0:
    ax2[1,ig].plot(it,psnr_osem, label = 'OSEM')
  ax2[1,ig].plot(it,psnr_spdhg[ig,:], label = f'SPD')
  ax2[1,ig].plot(it,psnr_spdhg_sparse[ig,:], label = f'SPDHG-S')

  if beta == 0:
    ax2[2,ig].plot(it,psnr_ps_osem, label = 'OSEM')
    ax2[2,ig].plot(it,psnr_ps_spdhg[ig,:], label = f'SPDHG')
    ax2[2,ig].plot(it,psnr_ps_spdhg_sparse[ig,:], label = f'SPDHG-S')
    ax2[2,0].set_ylabel('PSNR ps')

ax2[0,0].set_ylabel('cost')
ax2[1,0].set_ylabel('PSNR')
ax2[0,0].legend()

if beta == 0:
  for axx in ax2[0,:].flatten():
    axx.set_ylim(min(min(cost_osem), costs_spdhg.min(), costs_spdhg_sparse.min()), 
                 1.5*max(cost_osem) - 0.5*min(cost_osem))
else:
  for axx in ax2[0,:].flatten():
    axx.set_ylim(costs_spdhg[len(gammas)//2,:].min(),costs_spdhg[len(gammas)//2,2:].max())

for axx in ax2[-1,:].flatten():
  axx.set_xlabel('iteration')

for axx in ax2.flatten():
  axx.grid(ls = ':')

fig2.tight_layout()
fig2.savefig(os.path.join('figs',f'{base_str}_metrics.pdf'))
fig2.savefig(os.path.join('figs',f'{base_str}_metrics.png'))
fig2.show()            

# show the reconstructions
if  beta== 0:
  fig3, ax3 = plt.subplots(4,len(gammas) + 1, figsize = (len(gammas)*2,8))
else:
  fig3, ax3 = plt.subplots(2,len(gammas) + 1, figsize = (len(gammas)*2,4))

vmax = 1.5*img.max()

ax3[0,0].imshow(ref_recon, vmax = vmax, cmap = plt.cm.Greys)
ax3[0,0].set_title('REFERENCE', fontsize = 'small')
if beta == 0:
  ax3[1,0].imshow(recon_osem, vmax = vmax, cmap = plt.cm.Greys)
  ax3[1,0].set_title('OSEM', fontsize = 'small')
  ax3[2,0].imshow(gaussian_filter(ref_recon,sig), vmax = vmax, cmap = plt.cm.Greys)
  ax3[2,0].set_title('ps REFERNCE', fontsize = 'small')
  ax3[3,0].imshow(gaussian_filter(recon_osem,sig), vmax = vmax, cmap = plt.cm.Greys)
  ax3[3,0].set_title('ps OSEM', fontsize = 'small')

for ig, gamma in enumerate(gammas):
  ax3[0,ig+1].imshow(recons_spdhg[ig,...], vmax = vmax, cmap = plt.cm.Greys)
  ax3[1,ig+1].imshow(recons_spdhg_sparse[ig,...], vmax = vmax, cmap = plt.cm.Greys)
  ax3[0,ig+1].set_title(f'SPDHG {gamma:.1E}', fontsize = 'small')
  ax3[1,ig+1].set_title(f'SPDHG-S {gamma:.1E}', fontsize = 'small')

  if  beta== 0:
    ax3[2,ig+1].imshow(gaussian_filter(recons_spdhg[ig,...],sig), vmax = vmax, cmap = plt.cm.Greys)
    ax3[3,ig+1].imshow(gaussian_filter(recons_spdhg_sparse[ig,...],sig), vmax = vmax, cmap = plt.cm.Greys)
    ax3[2,ig+1].set_title(f'ps SPDHG {gamma:.1E}', fontsize = 'small')
    ax3[3,ig+1].set_title(f'ps SPDHG-S {gamma:.1E}', fontsize = 'small')

for axx in ax3.flatten():
  axx.set_axis_off()

fig3.tight_layout()
fig3.savefig(os.path.join('figs',f'{base_str}.png'))
fig3.show()

# show the early reconstructions
if  beta== 0:
  fig4, ax4 = plt.subplots(4,len(gammas) + 1, figsize = (len(gammas)*2,8))
else:
  fig4, ax4 = plt.subplots(2,len(gammas) + 1, figsize = (len(gammas)*2,4))

vmax = 1.5*img.max()

ax4[0,0].imshow(ref_recon, vmax = vmax, cmap = plt.cm.Greys)
ax4[0,0].set_title('REFERENCE', fontsize = 'small')
if beta == 0:
  ax4[1,0].imshow(recon_osem_early, vmax = vmax, cmap = plt.cm.Greys)
  ax4[1,0].set_title('OSEM', fontsize = 'small')
  ax4[2,0].imshow(gaussian_filter(ref_recon,sig), vmax = vmax, cmap = plt.cm.Greys)
  ax4[2,0].set_title('ps REFERNCE', fontsize = 'small')
  ax4[3,0].imshow(gaussian_filter(recon_osem_early,sig), vmax = vmax, cmap = plt.cm.Greys)
  ax4[3,0].set_title('ps OSEM', fontsize = 'small')

for ig, gamma in enumerate(gammas):
  ax4[0,ig+1].imshow(recons_spdhg_early[ig,...], vmax = vmax, cmap = plt.cm.Greys)
  ax4[1,ig+1].imshow(recons_spdhg_sparse_early[ig,...], vmax = vmax, cmap = plt.cm.Greys)
  ax4[0,ig+1].set_title(f'SPDHG {gamma:.1E}', fontsize = 'small')
  ax4[1,ig+1].set_title(f'SPDHG-S {gamma:.1E}', fontsize = 'small')

  if  beta== 0:
    ax4[2,ig+1].imshow(gaussian_filter(recons_spdhg_early[ig,...],sig), vmax = vmax, cmap = plt.cm.Greys)
    ax4[3,ig+1].imshow(gaussian_filter(recons_spdhg_sparse_early[ig,...],sig), vmax = vmax, cmap = plt.cm.Greys)
    ax4[2,ig+1].set_title(f'ps SPDHG {gamma:.1E}', fontsize = 'small')
    ax4[3,ig+1].set_title(f'ps SPDHG-S {gamma:.1E}', fontsize = 'small')

for axx in ax4.flatten():
  axx.set_axis_off()

fig4.tight_layout()
fig4.savefig(os.path.join('figs',f'{base_str}_early_{it_early}.png'))
fig4.show()


