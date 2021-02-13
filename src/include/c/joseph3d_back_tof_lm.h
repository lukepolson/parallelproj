#ifndef JOSEPH3D_BACK_TOF_LM
#define JOSEPH3D_BACK_TOF_LM

void joseph3d_back_tof_lm(const float *xstart, 
                          const float *xend, 
                          float *img,
                          const float *img_origin, 
                          const float *voxsize,
                          const float *p, 
                          long long nlors, 
                          const int *img_dim,
                          float tofbin_width,
                          const float *sigma_tof,
                          const float *tofcenter_offset,
                          float n_sigmas,
                          const short *tof_bin);
#endif