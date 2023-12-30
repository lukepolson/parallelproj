import parallelproj
import array_api_compat.numpy as np

from types import ModuleType

from config import pytestmark

def isclose(x: float,
            y: float,
            atol: float = 1e-8,
            rtol: float = 1e-5) -> bool:
    """check if two floating point numbers are close to each other, given absolute and relative error
       inspired by numpy.isclose
    """
    return bool(abs(x - y) <= (atol + rtol * abs(y)))


def test_tof_sino_fwd(xp: ModuleType,
                      dev: str,
                      verbose: bool = True,
                      atol: float = 1e-6) -> bool:
    """test fwd sinogram TOF projection of a point source"""
    nLORs: int = 1
    voxsize: float = 0.1

    n0, n1, n2 = (171, 171, 171)

    img_dim = (n0, n1, n2)
    voxel_size = xp.asarray([voxsize, voxsize, voxsize],
                            dtype=xp.float32,
                            device=dev)
    img_origin = (-xp.asarray(img_dim, dtype=xp.float32, device=dev) / 2 +
                  0.5) * voxel_size
    img = xp.zeros((n0, n1, n2), dtype=xp.float32, device=dev)
    img[n0 // 2, n1 // 2, n2 // 2] = 1

    xstart = xp.zeros((nLORs, 3), dtype=xp.float32, device=dev)
    xstart[:, 0] = 0
    xstart[:, 0] = 0
    xstart[:, 0] = 100

    xend = xp.zeros((nLORs, 3), dtype=xp.float32, device=dev)
    xend[:, 0] = 0
    xend[:, 0] = 0
    xend[:, 0] = -100

    # forward project
    tofbin_width = 0.05
    num_tof_bins = 501
    nsigmas = 9.
    fwhm_tof = 6.
    sigma_tof = xp.asarray([fwhm_tof / (2 * np.sqrt(2 * np.log(2)))],
                           dtype=xp.float32,
                           device=dev)
    tofcenter_offset = xp.asarray([0], dtype=xp.float32, device=dev)

    img_fwd = xp.zeros((xstart.shape[0], num_tof_bins),
                       dtype=xp.float32,
                       device=dev)

    img_fwd = parallelproj.joseph3d_fwd_tof_sino(xstart, xend, img, img_origin,
                                                 voxel_size, tofbin_width,
                                                 sigma_tof, tofcenter_offset,
                                                 nsigmas, num_tof_bins)

    # check if sum of the projection is correct (should be equal to the voxel size)
    res1 = isclose(xp.sum(img_fwd), voxsize)

    # check if the FWHM in the projected profile is correct
    # to do so, we check if the interpolated profile - 0.5 * max(profile) at +/- FWHM/2 is 0
    r = (xp.arange(num_tof_bins, dtype=xp.float32, device=dev) -
         0.5 * num_tof_bins + 0.5) * tofbin_width

    if parallelproj.is_cuda_array(img_fwd):
        import array_api_compat.cupy as cp

        res2 = isclose(float(
            cp.interp(cp.asarray([fwhm_tof / 2]), cp.asarray(r),
                      cp.asarray(img_fwd[0, :] -
                                 0.5 * xp.max(img_fwd[0, :])))[0]),
                       0,
                       atol=atol)
        res3 = isclose(float(
            cp.interp(cp.asarray([-fwhm_tof / 2]), cp.asarray(r),
                      cp.asarray(img_fwd[0, :] -
                                 0.5 * xp.max(img_fwd[0, :])))[0]),
                       0,
                       atol=atol)

    else:
        res2 = isclose(float(
            np.interp(np.asarray([fwhm_tof / 2]), r,
                      img_fwd[0, :] - 0.5 * xp.max(img_fwd[0, :]))[0]),
                       0,
                       atol=atol)
        res3 = isclose(float(
            np.interp(np.asarray([-fwhm_tof / 2]), r,
                      img_fwd[0, :] - 0.5 * xp.max(img_fwd[0, :]))[0]),
                       0,
                       atol=atol)

    if verbose:
        print(
            f'module = {xp.__name__}  -  cuda_enabled {parallelproj.num_visible_cuda_devices > 0}'
        )
        print(
            f'sum of TOF profile / expected:    {float(xp.sum(img_fwd)):.4E} / {voxsize:.4E}'
        )
        print('')

    assert bool(res1 * res2 * res3)


def test_adjointness(xp: ModuleType,
                     dev: str,
                     nLORs=1000000,
                     seed=1,
                     verbose=True) -> bool:
    """test whether backprojection is the adjoint of forward projection
       indirect test whether back projection is correct (assuming fwd projection is correct)
    """

    np.random.seed(seed)
    n0, n1, n2 = (16, 15, 17)

    img_dim = (n0, n1, n2)
    voxel_size = xp.asarray([0.7, 0.8, 0.6], dtype=xp.float32, device=dev)
    img_origin = (
        (-xp.asarray(img_dim, dtype=xp.float32, device=dev) / 2 + 0.5) *
        voxel_size)

    img = xp.asarray(np.random.rand(n0, n1, n2), dtype=xp.float32, device=dev)

    # generate random LORs on a sphere around the image volume
    R = 0.8 * xp.max(
        (xp.asarray(img_dim, dtype=xp.float32, device=dev) * voxel_size))

    phis = xp.asarray(np.random.rand(nLORs) * 2 * np.pi, device=dev)
    costheta = xp.asarray(np.random.rand(nLORs) * 2 - 1, device=dev)
    sintheta = xp.sqrt(1 - costheta**2)

    xstart = xp.zeros((nLORs, 3), dtype=xp.float32, device=dev)
    xstart[:, 0] = R * sintheta * xp.cos(phis)
    xstart[:, 1] = R * sintheta * xp.sin(phis)
    xstart[:, 2] = R * costheta

    phis = xp.asarray(np.random.rand(nLORs) * 2 * np.pi, device=dev)
    costheta = xp.asarray(np.random.rand(nLORs) * 2 - 1, device=dev)
    sintheta = xp.sqrt(1 - costheta**2)

    xend = xp.zeros((nLORs, 3), dtype=xp.float32, device=dev)
    xend[:, 0] = R * sintheta * xp.cos(phis)
    xend[:, 1] = R * sintheta * xp.sin(phis)
    xend[:, 2] = R * costheta

    # TOF parameters
    tofbin_width = 2.
    num_tof_bins = 11
    nsigmas = 3.
    sigma_tof = xp.asarray([5 / 2.35], dtype=xp.float32, device=dev)
    tofcenter_offset = xp.asarray([0], dtype=xp.float32, device=dev)

    # forward project
    img_fwd = parallelproj.joseph3d_fwd_tof_sino(xstart, xend, img, img_origin,
                                                 voxel_size, tofbin_width,
                                                 sigma_tof, tofcenter_offset,
                                                 nsigmas, num_tof_bins)

    # backward project
    sino = xp.asarray(np.random.rand(*img_fwd.shape),
                      dtype=xp.float32,
                      device=dev)
    back_img = parallelproj.joseph3d_back_tof_sino(xstart, xend, img.shape,
                                                   img_origin, voxel_size,
                                                   sino, tofbin_width,
                                                   sigma_tof, tofcenter_offset,
                                                   nsigmas, num_tof_bins)

    ip_a = float(xp.sum((back_img * img)))
    ip_b = float(xp.sum((img_fwd * sino)))

    if verbose:
        print(
            f'module = {xp.__name__}  -  cuda_enabled {parallelproj.num_visible_cuda_devices > 0}'
        )
        print('ip_a = ', ip_a)
        print('ip_b = ', ip_b)
        print('')

    assert isclose(ip_a, ip_b)
