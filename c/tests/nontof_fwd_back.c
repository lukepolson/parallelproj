#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "parallelproj_c.h"

// test nontof projectors using a simple 2D image along one direction
int main()
{
    int retval = 0;

    float eps = 1e-7;

    const int img_dim[] = {2, 3, 4};
    const float voxsize[] = {4, 3, 2};
    //--------------------------------------------------------------------------
    //--------------------------------------------------------------------------
    //--------------------------------------------------------------------------

    int n0 = img_dim[0];
    int n1 = img_dim[1];
    int n2 = img_dim[2];

    const float img_origin[] = {(-(float)img_dim[0] / 2 + 0.5) * voxsize[0],
                                (-(float)img_dim[1] / 2 + 0.5) * voxsize[1],
                                (-(float)img_dim[2] / 2 + 0.5) * voxsize[2]};

    printf("\nimage dimension: ");
    printf("%d %d %d\n", img_dim[0], img_dim[1], img_dim[2]);

    printf("\nvoxel size: ");
    printf("%.1f %.1f %.1f\n", voxsize[0], voxsize[1], voxsize[2]);

    printf("\nimage origin: ");
    printf("%.1f %.1f %.1f\n", img_origin[0], img_origin[1], img_origin[2]);

    float *img = (float *)calloc(n0 * n1 * n2, sizeof(float));

    printf("\nimage:\n");
    for (int i0 = 0; i0 < img_dim[0]; i0++)
    {
        for (int i1 = 0; i1 < img_dim[1]; i1++)
        {
            for (int i2 = 0; i2 < img_dim[2]; i2++)
            {
                img[n1 * n2 * i0 + n2 * i1 + i2] = (n1 * n2 * i0 + n2 * i1 + i2 + 1);
                printf("%.1f ", img[n1 * n2 * i0 + n2 * i1 + i2]);
            }
            printf("\n");
        }
        printf("\n");
    }

    // setup the start and end coordinates of a few test rays in voxel coordinates
    long long nlors = 4;

    int istart[] = {0, -1, 0, // first two test rays are the same to check for race condiations in the back projection
                    0, -1, 0, //
                    0, 0, -1, //
                    -1, 0, 0};

    int iend[] = {0, n1, 0, //
                  0, n1, 0, //
                  0, 0, n2, //
                  n0, 0, 0};

    for (int ir = 0; ir < nlors; ir++)
    {
        printf("test ray %d\n", ir);
        printf("start .: %d %d %d\n", istart[ir * 3 + 0], istart[ir * 3 + 1], istart[ir * 3 + 2]);
        printf("end   .: %d %d %d\n", iend[ir * 3 + 0], iend[ir * 3 + 1], iend[ir * 3 + 2]);
    }

    // calculate the start and end coordinates in world coordinates
    float *xstart = (float *)calloc(3 * nlors, sizeof(float));
    float *xend = (float *)calloc(3 * nlors, sizeof(float));

    for (int ir = 0; ir < nlors; ir++)
    {
        for (int j = 0; j < 3; j++)
        {
            xstart[ir * 3 + j] = img_origin[j] + istart[ir * 3 + j] * voxsize[j];
            xend[ir * 3 + j] = img_origin[j] + iend[ir * 3 + j] * voxsize[j];
        }
    }

    // allocate memory for the forward projection
    float *p = (float *)calloc(nlors, sizeof(float));

    // forward projection test
    joseph3d_fwd(xstart, xend, img, img_origin, voxsize, p, nlors, img_dim);

    printf("\nforward projected values:\n");
    for (int i = 0; i < nlors; i++)
    {
        printf("%.1f ", p[i]);
    }

    // calculate the expected value of the first and second rays that project from [0,-1,0] to [0,last,0]
    float *expected_fwd_vals = (float *)calloc(nlors, sizeof(float));
    for (int i1 = 0; i1 < img_dim[1]; i1++)
    {
        expected_fwd_vals[0] += img[0 * n1 * n2 + i1 * n2 + 0] * voxsize[1];
    }

    expected_fwd_vals[1] = expected_fwd_vals[0];

    for (int i2 = 0; i2 < img_dim[2]; i2++)
    {
        expected_fwd_vals[2] += img[0 * n1 * n2 + 0 * n2 + i2] * voxsize[2];
    }

    // calculate the expected value of the first and second rays that project from [1,1,-1] to [1,1,last]
    for (int i0 = 0; i0 < img_dim[0]; i0++)
    {
        expected_fwd_vals[3] += img[i0 * n1 * n2 + 0 * n2 + 0] * voxsize[0];
    }

    // check if we got the expected results
    float fwd_diff = 0;
    for (int ir = 0; ir < nlors; ir++)
    {

        fwd_diff = fabs(p[ir] - expected_fwd_vals[ir]);
        if (fwd_diff > eps)
        {
            printf("\n################################################################################");
            printf("\nabs(fwd projected - expected value) = %.2e for ray%d above tolerance %.2e", fwd_diff, ir, eps);
            printf("\n################################################################################");
            retval = 1;
        }
    }

    //// back projection test
    // float bimg[] = {0, 0, 0,
    //                 0, 0, 0,
    //                 0, 0, 0,

    //                0, 0, 0,
    //                0, 0, 0,
    //                0, 0, 0,

    //                0, 0, 0,
    //                0, 0, 0,
    //                0, 0, 0};

    // float *ones = (float *)calloc(nlors, sizeof(float));
    // for (int i = 0; i < nlors; i++)
    //{
    //     ones[i] = 1;
    // }

    // joseph3d_back(xstart, xend, bimg, img_origin, voxsize, ones, nlors, img_dim);

    // printf("\n%.1f %.1f %.1f\n", bimg[0 + 9], bimg[1 + 9], bimg[2 + 9]);
    // printf("%.1f %.1f %.1f\n", bimg[3 + 9], bimg[4 + 9], bimg[5 + 9]);
    // printf("%.1f %.1f %.1f\n", bimg[6 + 9], bimg[7 + 9], bimg[8 + 9]);

    // if (bimg[0 + 9] != 6)
    //     retval = 1;
    // if (bimg[1 + 9] != 3)
    //     retval = 1;
    // if (bimg[2 + 9] != 1)
    //     retval = 1;
    // if (bimg[3 + 9] != 6)
    //     retval = 1;
    // if (bimg[4 + 9] != 3)
    //     retval = 1;
    // if (bimg[5 + 9] != 1)
    //     retval = 1;
    // if (bimg[6 + 9] != 6)
    //     retval = 1;
    // if (bimg[7 + 9] != 3)
    //     retval = 1;
    // if (bimg[8 + 9] != 1)
    //     retval = 1;

    return retval;
}
