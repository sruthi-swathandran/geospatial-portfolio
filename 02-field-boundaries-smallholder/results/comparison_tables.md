# Generated tables for COMPARISON.md

Rebuild with `python src\build_comparison.py`. Do not edit by hand.

## India, every setting

1,983 labelled parcels.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL |  | 175 | 0.000 | 0.027 | 0.022 | +0.005 |
| watershed | 0.005 | 917 | 0.349 | 0.233 | 0.051 | +0.182 |
| watershed | 0.01 | 816 | 0.349 | 0.244 | 0.051 | +0.193 |
| watershed | 0.02 | 676 | 0.333 | 0.246 | 0.051 | +0.196 |
| watershed | 0.05 | 446 | 0.296 | 0.219 | 0.037 | +0.182 |
| watershed | 0.08 | 319 | 0.235 | 0.182 | 0.033 | +0.149 |
| watershed | 0.1 | 261 | 0.195 | 0.156 | 0.025 | +0.131 |
| watershed | 0.13 | 196 | 0.134 | 0.124 | 0.018 | +0.106 |
| watershed | 0.16 | 149 | 0.089 | 0.088 | 0.016 | +0.072 |
| watershed | 0.2 | 103 | 0.048 | 0.053 | 0.007 | +0.046 |
| watershed | 0.3 | 40 | 0.009 | 0.019 | 0.001 | +0.018 |
| felzenszwalb | 25 | 1,404 | 0.234 | 0.028 | 0.057 | -0.029 |
| felzenszwalb | 50 | 1,165 | 0.266 | 0.061 | 0.053 | +0.009 |
| felzenszwalb | 100 | 666 | 0.218 | 0.084 | 0.045 | +0.039 |
| felzenszwalb | 150 | 437 | 0.144 | 0.065 | 0.037 | +0.028 |
| felzenszwalb | 200 | 323 | 0.103 | 0.052 | 0.031 | +0.021 |
| felzenszwalb | 300 | 213 | 0.047 | 0.042 | 0.022 | +0.020 |
| felzenszwalb | 400 | 163 | 0.019 | 0.027 | 0.014 | +0.013 |
| felzenszwalb | 800 | 96 | 0.004 | 0.012 | 0.006 | +0.006 |
| SAM ViT-H true colour | 0.50/0.88 | 185 | 0.051 | 0.156 | 0.019 | +0.137 |
| SAM ViT-H true colour | 0.60/0.88 | 184 | 0.051 | 0.156 | 0.022 | +0.134 |
| SAM ViT-H true colour | 0.70/0.88 | 181 | 0.043 | 0.155 | 0.018 | +0.136 |
| SAM ViT-H true colour | 0.80/0.88 | 167 | 0.023 | 0.146 | 0.015 | +0.131 |
| SAM ViT-H true colour | 0.88/0.88 | 129 | 0.008 | 0.121 | 0.012 | +0.110 |
| SAM ViT-H false colour | 0.50/0.88 | 213 | 0.127 | 0.172 | 0.021 | +0.151 |
| SAM ViT-H false colour | 0.60/0.88 | 212 | 0.127 | 0.172 | 0.025 | +0.147 |
| SAM ViT-H false colour | 0.70/0.88 | 208 | 0.118 | 0.170 | 0.023 | +0.147 |
| SAM ViT-H false colour | 0.80/0.88 | 192 | 0.103 | 0.162 | 0.021 | +0.142 |
| SAM ViT-H false colour | 0.88/0.88 | 147 | 0.038 | 0.139 | 0.015 | +0.123 |

## India, at FTW's object budget

| method | recall at 175 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.027 | 0.022 | +0.005 | single setting |
| watershed | 0.107 | 0.017 | +0.091 | interpolated |
| felzenszwalb | 0.031 | 0.016 | +0.015 | interpolated |
| SAM ViT-H true colour | 0.151 | 0.017 | +0.134 | interpolated |
| SAM ViT-H false colour | 0.153 | 0.019 | +0.135 | interpolated |

## India, recall by ground width

SAM at threshold 0.50, classical methods at their best setting.

| ground width | parcels | FTW 3-class FULL | watershed | SAM ViT-H true colour | SAM ViT-H false colour |
|---|---:|---:|---:|---:|---:|
| under 20 m | 196 | 0.00% | 1.02% | 0.51% | 1.02% |
| 20 to 30 m | 245 | 0.41% | 4.90% | 2.04% | 0.82% |
| 30 to 50 m | 867 | 0.58% | 22.49% | 8.77% | 10.61% |
| 50 m up | 675 | 7.11% | 41.33% | 33.78% | 36.44% |

## India, the same widths cut finer

SAM at threshold 0.50, classical methods at their best setting.

| width, native 10 m px | parcels | FTW 3-class FULL | watershed | SAM ViT-H true colour | SAM ViT-H false colour |
|---|---:|---:|---:|---:|---:|
| under 2 | 196 | 0.00% | 1.02% | 0.51% | 1.02% |
| 2 to 3 | 245 | 0.41% | 4.90% | 2.04% | 0.82% |
| 3 to 4 | 503 | 0.20% | 17.10% | 6.56% | 7.16% |
| 4 to 5 | 364 | 1.10% | 29.95% | 11.81% | 15.38% |
| 5 to 7 | 347 | 3.75% | 48.41% | 25.07% | 26.80% |
| 7 to 10 | 202 | 6.44% | 40.59% | 38.12% | 44.06% |
| 10 and over | 126 | 17.46% | 23.02% | 50.79% | 50.79% |

## Slovenia, every setting

6,831 labelled parcels.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL |  | 18 | 0.000 | 0.222 | 0.005 | +0.217 |
| watershed | 0.005 | 706 | 0.302 | 0.202 | 0.025 | +0.177 |
| watershed | 0.01 | 620 | 0.325 | 0.242 | 0.026 | +0.216 |
| watershed | 0.02 | 492 | 0.355 | 0.292 | 0.025 | +0.267 |
| watershed | 0.05 | 282 | 0.356 | 0.345 | 0.020 | +0.325 |
| watershed | 0.08 | 180 | 0.303 | 0.328 | 0.018 | +0.310 |
| watershed | 0.1 | 140 | 0.254 | 0.305 | 0.014 | +0.291 |
| watershed | 0.13 | 101 | 0.191 | 0.257 | 0.011 | +0.245 |
| watershed | 0.16 | 76 | 0.150 | 0.217 | 0.009 | +0.208 |
| watershed | 0.2 | 54 | 0.103 | 0.170 | 0.009 | +0.161 |
| watershed | 0.3 | 26 | 0.031 | 0.081 | 0.003 | +0.078 |
| felzenszwalb | 25 | 581 | 0.193 | 0.030 | 0.024 | +0.006 |
| felzenszwalb | 50 | 567 | 0.284 | 0.110 | 0.024 | +0.086 |
| felzenszwalb | 100 | 382 | 0.298 | 0.209 | 0.023 | +0.186 |
| felzenszwalb | 150 | 268 | 0.238 | 0.201 | 0.022 | +0.180 |
| felzenszwalb | 200 | 202 | 0.179 | 0.177 | 0.019 | +0.158 |
| felzenszwalb | 300 | 135 | 0.107 | 0.128 | 0.015 | +0.112 |
| felzenszwalb | 400 | 101 | 0.066 | 0.097 | 0.011 | +0.086 |
| felzenszwalb | 800 | 54 | 0.016 | 0.035 | 0.005 | +0.030 |
| SAM ViT-H true colour | 0.50/0.88 | 112 | 0.194 | 0.276 | 0.013 | +0.263 |
| SAM ViT-H true colour | 0.60/0.88 | 112 | 0.193 | 0.275 | 0.013 | +0.263 |
| SAM ViT-H true colour | 0.70/0.88 | 110 | 0.189 | 0.274 | 0.013 | +0.260 |
| SAM ViT-H true colour | 0.80/0.88 | 105 | 0.172 | 0.264 | 0.014 | +0.250 |
| SAM ViT-H true colour | 0.88/0.88 | 85 | 0.118 | 0.233 | 0.010 | +0.223 |
| SAM ViT-H false colour | 0.50/0.88 | 112 | 0.154 | 0.248 | 0.012 | +0.236 |
| SAM ViT-H false colour | 0.60/0.88 | 112 | 0.154 | 0.248 | 0.012 | +0.236 |
| SAM ViT-H false colour | 0.70/0.88 | 110 | 0.151 | 0.246 | 0.013 | +0.233 |
| SAM ViT-H false colour | 0.80/0.88 | 102 | 0.129 | 0.236 | 0.012 | +0.224 |
| SAM ViT-H false colour | 0.88/0.88 | 82 | 0.084 | 0.206 | 0.011 | +0.196 |

## Slovenia, at FTW's object budget

| method | recall at 18 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.222 | 0.005 | +0.217 | single setting |
| watershed | 0.081 | 0.003 | +0.078 | clamped, sweep stops at 26 objects |
| felzenszwalb | 0.035 | 0.005 | +0.030 | clamped, sweep stops at 54 objects |
| SAM ViT-H true colour | 0.233 | 0.010 | +0.223 | clamped, sweep stops at 85 objects |
| SAM ViT-H false colour | 0.206 | 0.011 | +0.196 | clamped, sweep stops at 82 objects |

## Slovenia, recall by ground width

SAM at threshold 0.50, classical methods at their best setting.

| ground width | parcels | FTW 3-class FULL | watershed | SAM ViT-H true colour | SAM ViT-H false colour |
|---|---:|---:|---:|---:|---:|
| under 20 m | 2,842 | 1.48% | 5.42% | 3.80% | 2.74% |
| 20 to 30 m | 1,590 | 12.89% | 35.97% | 24.40% | 21.01% |
| 30 to 50 m | 1,261 | 41.24% | 63.36% | 47.26% | 41.87% |
| 50 m up | 1,138 | 65.91% | 73.11% | 69.51% | 66.52% |

## Slovenia, the same widths cut finer

SAM at threshold 0.50, classical methods at their best setting.

| width, native 10 m px | parcels | FTW 3-class FULL | watershed | SAM ViT-H true colour | SAM ViT-H false colour |
|---|---:|---:|---:|---:|---:|
| under 2 | 2,842 | 1.48% | 5.42% | 3.80% | 2.74% |
| 2 to 3 | 1,590 | 12.89% | 35.97% | 24.40% | 21.01% |
| 3 to 4 | 706 | 36.26% | 60.06% | 42.63% | 34.56% |
| 4 to 5 | 555 | 47.57% | 67.57% | 53.15% | 51.17% |
| 5 to 7 | 620 | 62.10% | 72.90% | 63.71% | 61.61% |
| 7 to 10 | 369 | 69.65% | 77.51% | 76.15% | 71.27% |
| 10 and over | 149 | 72.48% | 63.09% | 77.18% | 75.17% |

## The same width band in both countries

Same sensor, same method, same physical parcel size.

| ground width | method | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| under 20 m | FTW 3-class FULL | 0/196, 0.00% | 42/2,842, 1.48% | not readable |
| 20 to 30 m | FTW 3-class FULL | 1/245, 0.41% | 205/1,590, 12.89% | 31.6x |
| 30 to 50 m | FTW 3-class FULL | 5/867, 0.58% | 520/1,261, 41.24% | 71.5x |
| 50 m up | FTW 3-class FULL | 48/675, 7.11% | 750/1,138, 65.91% | 9.3x |
| under 20 m | watershed | 2/196, 1.02% | 154/2,842, 5.42% | 5.3x |
| 20 to 30 m | watershed | 12/245, 4.90% | 572/1,590, 35.97% | 7.3x |
| 30 to 50 m | watershed | 195/867, 22.49% | 799/1,261, 63.36% | 2.8x |
| 50 m up | watershed | 279/675, 41.33% | 832/1,138, 73.11% | 1.8x |
| under 20 m | SAM ViT-H true colour | 1/196, 0.51% | 108/2,842, 3.80% | 7.4x |
| 20 to 30 m | SAM ViT-H true colour | 5/245, 2.04% | 388/1,590, 24.40% | 12.0x |
| 30 to 50 m | SAM ViT-H true colour | 76/867, 8.77% | 596/1,261, 47.26% | 5.4x |
| 50 m up | SAM ViT-H true colour | 228/675, 33.78% | 791/1,138, 69.51% | 2.1x |
