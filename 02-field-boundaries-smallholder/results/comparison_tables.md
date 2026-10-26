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
| SAM ViT-H natural colour | 0.50/0.88 | 195 | 0.089 | 0.167 | 0.020 | +0.147 |
| SAM ViT-H natural colour | 0.60/0.88 | 194 | 0.089 | 0.166 | 0.021 | +0.145 |
| SAM ViT-H natural colour | 0.70/0.88 | 190 | 0.085 | 0.164 | 0.018 | +0.146 |
| SAM ViT-H natural colour | 0.80/0.88 | 176 | 0.056 | 0.152 | 0.018 | +0.135 |
| SAM ViT-H natural colour | 0.88/0.88 | 135 | 0.010 | 0.130 | 0.012 | +0.117 |
| SAM ViT-H colour infrared | 0.50/0.88 | 222 | 0.149 | 0.183 | 0.028 | +0.155 |
| SAM ViT-H colour infrared | 0.60/0.88 | 222 | 0.148 | 0.183 | 0.026 | +0.157 |
| SAM ViT-H colour infrared | 0.70/0.88 | 218 | 0.144 | 0.181 | 0.019 | +0.162 |
| SAM ViT-H colour infrared | 0.80/0.88 | 201 | 0.123 | 0.174 | 0.022 | +0.152 |
| SAM ViT-H colour infrared | 0.88/0.88 | 155 | 0.055 | 0.145 | 0.017 | +0.128 |
| SAM ViT-H, blue-green-red | 0.50/0.88 | 184 | 0.051 | 0.156 | 0.019 | +0.137 |
| SAM ViT-H, blue-green-red | 0.60/0.88 | 184 | 0.051 | 0.156 | 0.022 | +0.134 |
| SAM ViT-H, blue-green-red | 0.70/0.88 | 180 | 0.043 | 0.155 | 0.018 | +0.136 |
| SAM ViT-H, blue-green-red | 0.80/0.88 | 167 | 0.023 | 0.146 | 0.015 | +0.131 |
| SAM ViT-H, blue-green-red | 0.88/0.88 | 129 | 0.008 | 0.121 | 0.012 | +0.110 |
| SAM ViT-H, NIR-blue-green | 0.50/0.88 | 213 | 0.127 | 0.172 | 0.021 | +0.151 |
| SAM ViT-H, NIR-blue-green | 0.60/0.88 | 212 | 0.127 | 0.172 | 0.025 | +0.147 |
| SAM ViT-H, NIR-blue-green | 0.70/0.88 | 208 | 0.118 | 0.170 | 0.023 | +0.147 |
| SAM ViT-H, NIR-blue-green | 0.80/0.88 | 192 | 0.103 | 0.162 | 0.021 | +0.142 |
| SAM ViT-H, NIR-blue-green | 0.88/0.88 | 147 | 0.038 | 0.139 | 0.015 | +0.123 |

## India, at FTW's object budget

| method | recall at 175 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.027 | 0.022 | +0.005 | single setting |
| watershed | 0.107 | 0.017 | +0.091 | interpolated |
| felzenszwalb | 0.031 | 0.016 | +0.015 | interpolated |
| SAM ViT-H natural colour | 0.152 | 0.017 | +0.134 | interpolated |
| SAM ViT-H colour infrared | 0.158 | 0.019 | +0.138 | interpolated |
| SAM ViT-H, blue-green-red | 0.151 | 0.017 | +0.134 | interpolated |
| SAM ViT-H, NIR-blue-green | 0.153 | 0.019 | +0.135 | interpolated |

## India, recall by ground width

SAM at threshold 0.50, classical methods at their best setting.

| ground width | parcels | FTW 3-class FULL | watershed | SAM ViT-H natural colour | SAM ViT-H colour infrared | SAM ViT-H, blue-green-red | SAM ViT-H, NIR-blue-green |
|---|---:|---:|---:|---:|---:|---:|---:|
| under 20 m | 196 | 0.00% | 1.02% | 0.51% | 1.02% | 0.51% | 1.02% |
| 20 to 30 m | 245 | 0.41% | 4.90% | 1.63% | 1.63% | 2.04% | 0.82% |
| 30 to 50 m | 867 | 0.58% | 22.49% | 9.23% | 10.96% | 8.77% | 10.61% |
| 50 m up | 675 | 7.11% | 41.33% | 36.44% | 38.81% | 33.78% | 36.44% |

## India, the same widths cut finer

SAM at threshold 0.50, classical methods at their best setting.

| width, native 10 m px | parcels | FTW 3-class FULL | watershed | SAM ViT-H natural colour | SAM ViT-H colour infrared | SAM ViT-H, blue-green-red | SAM ViT-H, NIR-blue-green |
|---|---:|---:|---:|---:|---:|---:|---:|
| under 2 | 196 | 0.00% | 1.02% | 0.51% | 1.02% | 0.51% | 1.02% |
| 2 to 3 | 245 | 0.41% | 4.90% | 1.63% | 1.63% | 2.04% | 0.82% |
| 3 to 4 | 503 | 0.20% | 17.10% | 6.96% | 7.75% | 6.56% | 7.16% |
| 4 to 5 | 364 | 1.10% | 29.95% | 12.36% | 15.38% | 11.81% | 15.38% |
| 5 to 7 | 347 | 3.75% | 48.41% | 27.38% | 29.39% | 25.07% | 26.80% |
| 7 to 10 | 202 | 6.44% | 40.59% | 43.07% | 46.53% | 38.12% | 44.06% |
| 10 and over | 126 | 17.46% | 23.02% | 50.79% | 52.38% | 50.79% | 50.79% |

## Slovenia, every setting

6,831 labelled parcels.

| method | setting | objects/chip | median IoU | recall | null | gap |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL |  | 20 | 0.000 | 0.222 | 0.007 | +0.215 |
| watershed | 0.005 | 785 | 0.311 | 0.209 | 0.025 | +0.184 |
| watershed | 0.01 | 672 | 0.333 | 0.248 | 0.025 | +0.223 |
| watershed | 0.02 | 521 | 0.360 | 0.297 | 0.024 | +0.273 |
| watershed | 0.05 | 291 | 0.360 | 0.348 | 0.020 | +0.328 |
| watershed | 0.08 | 184 | 0.307 | 0.331 | 0.016 | +0.315 |
| watershed | 0.1 | 143 | 0.258 | 0.307 | 0.015 | +0.292 |
| watershed | 0.13 | 102 | 0.194 | 0.259 | 0.012 | +0.246 |
| watershed | 0.16 | 77 | 0.151 | 0.219 | 0.009 | +0.210 |
| watershed | 0.2 | 55 | 0.104 | 0.171 | 0.006 | +0.165 |
| watershed | 0.3 | 26 | 0.031 | 0.081 | 0.003 | +0.078 |
| felzenszwalb | 25 | 902 | 0.217 | 0.035 | 0.024 | +0.011 |
| felzenszwalb | 50 | 762 | 0.295 | 0.116 | 0.025 | +0.091 |
| felzenszwalb | 100 | 462 | 0.305 | 0.214 | 0.022 | +0.192 |
| felzenszwalb | 150 | 314 | 0.243 | 0.203 | 0.024 | +0.180 |
| felzenszwalb | 200 | 234 | 0.181 | 0.178 | 0.020 | +0.158 |
| felzenszwalb | 300 | 156 | 0.109 | 0.129 | 0.015 | +0.114 |
| felzenszwalb | 400 | 118 | 0.066 | 0.098 | 0.013 | +0.085 |
| felzenszwalb | 800 | 65 | 0.017 | 0.037 | 0.006 | +0.030 |
| SAM ViT-H natural colour | 0.50/0.88 | 113 | 0.233 | 0.295 | 0.013 | +0.282 |
| SAM ViT-H natural colour | 0.60/0.88 | 113 | 0.232 | 0.295 | 0.014 | +0.281 |
| SAM ViT-H natural colour | 0.70/0.88 | 112 | 0.231 | 0.295 | 0.015 | +0.280 |
| SAM ViT-H natural colour | 0.80/0.88 | 106 | 0.209 | 0.286 | 0.013 | +0.272 |
| SAM ViT-H natural colour | 0.88/0.88 | 86 | 0.157 | 0.257 | 0.013 | +0.244 |
| SAM ViT-H colour infrared | 0.50/0.88 | 102 | 0.170 | 0.259 | 0.012 | +0.247 |
| SAM ViT-H colour infrared | 0.60/0.88 | 101 | 0.169 | 0.259 | 0.013 | +0.246 |
| SAM ViT-H colour infrared | 0.70/0.88 | 99 | 0.166 | 0.257 | 0.012 | +0.245 |
| SAM ViT-H colour infrared | 0.80/0.88 | 92 | 0.143 | 0.248 | 0.012 | +0.236 |
| SAM ViT-H colour infrared | 0.88/0.88 | 74 | 0.097 | 0.212 | 0.011 | +0.201 |
| SAM ViT-H, blue-green-red | 0.50/0.88 | 103 | 0.194 | 0.276 | 0.013 | +0.264 |
| SAM ViT-H, blue-green-red | 0.60/0.88 | 103 | 0.194 | 0.276 | 0.014 | +0.262 |
| SAM ViT-H, blue-green-red | 0.70/0.88 | 102 | 0.190 | 0.274 | 0.012 | +0.262 |
| SAM ViT-H, blue-green-red | 0.80/0.88 | 96 | 0.173 | 0.264 | 0.012 | +0.252 |
| SAM ViT-H, blue-green-red | 0.88/0.88 | 79 | 0.119 | 0.234 | 0.010 | +0.224 |
| SAM ViT-H, NIR-blue-green | 0.50/0.88 | 101 | 0.155 | 0.249 | 0.014 | +0.235 |
| SAM ViT-H, NIR-blue-green | 0.60/0.88 | 100 | 0.155 | 0.248 | 0.012 | +0.237 |
| SAM ViT-H, NIR-blue-green | 0.70/0.88 | 99 | 0.151 | 0.246 | 0.013 | +0.234 |
| SAM ViT-H, NIR-blue-green | 0.80/0.88 | 92 | 0.130 | 0.236 | 0.013 | +0.223 |
| SAM ViT-H, NIR-blue-green | 0.88/0.88 | 73 | 0.085 | 0.206 | 0.010 | +0.196 |

## Slovenia, at FTW's object budget

| method | recall at 20 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.222 | 0.007 | +0.215 | single setting |
| watershed | 0.081 | 0.003 | +0.078 | clamped, sweep stops at 26 objects |
| felzenszwalb | 0.037 | 0.006 | +0.030 | clamped, sweep stops at 65 objects |
| SAM ViT-H natural colour | 0.257 | 0.013 | +0.244 | clamped, sweep stops at 86 objects |
| SAM ViT-H colour infrared | 0.212 | 0.011 | +0.201 | clamped, sweep stops at 74 objects |
| SAM ViT-H, blue-green-red | 0.234 | 0.010 | +0.224 | clamped, sweep stops at 79 objects |
| SAM ViT-H, NIR-blue-green | 0.206 | 0.010 | +0.196 | clamped, sweep stops at 73 objects |

## Slovenia, recall by ground width

SAM at threshold 0.50, classical methods at their best setting.

| ground width | parcels | FTW 3-class FULL | watershed | SAM ViT-H natural colour | SAM ViT-H colour infrared | SAM ViT-H, blue-green-red | SAM ViT-H, NIR-blue-green |
|---|---:|---:|---:|---:|---:|---:|---:|
| under 20 m | 2,163 | 0.51% | 3.74% | 2.82% | 1.90% | 2.64% | 1.62% |
| 20 to 30 m | 1,229 | 7.89% | 21.32% | 15.62% | 11.96% | 14.56% | 12.12% |
| 30 to 50 m | 1,740 | 23.62% | 47.64% | 34.48% | 29.60% | 32.01% | 27.76% |
| 50 m up | 1,699 | 58.80% | 71.10% | 68.57% | 62.86% | 64.39% | 60.68% |

## Slovenia, the same widths cut finer

SAM at threshold 0.50, classical methods at their best setting.

| width, native 10 m px | parcels | FTW 3-class FULL | watershed | SAM ViT-H natural colour | SAM ViT-H colour infrared | SAM ViT-H, blue-green-red | SAM ViT-H, NIR-blue-green |
|---|---:|---:|---:|---:|---:|---:|---:|
| under 2 | 2,163 | 0.51% | 3.74% | 2.82% | 1.90% | 2.64% | 1.62% |
| 2 to 3 | 1,229 | 7.89% | 21.32% | 15.62% | 11.96% | 14.56% | 12.12% |
| 3 to 4 | 1,193 | 18.86% | 42.92% | 29.76% | 25.31% | 27.75% | 24.14% |
| 4 to 5 | 547 | 34.00% | 57.95% | 44.79% | 38.94% | 41.32% | 35.65% |
| 5 to 7 | 827 | 48.49% | 68.80% | 59.73% | 52.24% | 55.86% | 50.67% |
| 7 to 10 | 553 | 66.18% | 75.23% | 74.86% | 70.71% | 69.80% | 67.09% |
| 10 and over | 319 | 72.73% | 69.91% | 80.56% | 76.80% | 77.12% | 75.55% |

## The same width band in both countries

Same sensor, same method, same physical parcel size.

| ground width | method | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| under 20 m | FTW 3-class FULL | 0/196, 0.00% | 11/2,163, 0.51% | not readable |
| 20 to 30 m | FTW 3-class FULL | 1/245, 0.41% | 97/1,229, 7.89% | 19.3x |
| 30 to 50 m | FTW 3-class FULL | 5/867, 0.58% | 411/1,740, 23.62% | 41.0x |
| 50 m up | FTW 3-class FULL | 48/675, 7.11% | 999/1,699, 58.80% | 8.3x |
| under 20 m | watershed | 2/196, 1.02% | 81/2,163, 3.74% | 3.7x |
| 20 to 30 m | watershed | 12/245, 4.90% | 262/1,229, 21.32% | 4.4x |
| 30 to 50 m | watershed | 195/867, 22.49% | 829/1,740, 47.64% | 2.1x |
| 50 m up | watershed | 279/675, 41.33% | 1208/1,699, 71.10% | 1.7x |
| under 20 m | SAM ViT-H natural colour | 1/196, 0.51% | 61/2,163, 2.82% | 5.5x |
| 20 to 30 m | SAM ViT-H natural colour | 4/245, 1.63% | 192/1,229, 15.62% | 9.6x |
| 30 to 50 m | SAM ViT-H natural colour | 80/867, 9.23% | 600/1,740, 34.48% | 3.7x |
| 50 m up | SAM ViT-H natural colour | 246/675, 36.44% | 1165/1,699, 68.57% | 1.9x |

## India, what the methods emit

| method | objects/chip | no object | exactly one | 5 or more | matched share | parcels |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL | 175.0 | 74.4% | 18.9% | 0.3% | 0.08% | 1,983 |
| SAM ViT-H NIR-blue-green 0.50 (subset) | 190.4 | 8.7% | 33.0% | 8.5% | 0.42% | 494 |
| SAM ViT-H colour infrared 0.50 (subset) | 195.6 | 10.1% | 30.0% | 8.9% | 0.41% | 494 |
| watershed 0.02 | 675.9 | 0.0% | 7.2% | 38.2% | 0.18% | 1,983 |

## India, held-out setting choice

| method | published | held out | optimism | setting |
|---|---:|---:|---:|---|
| watershed | 0.2461 | 0.2444 | +0.0016 | 0.02 in 62% of splits |
| felzenszwalb | 0.0842 | 0.0848 | -0.0005 | 100.0 in 100% of splits |
| SAM ViT-H blue-green-red | 0.1563 | 0.1574 | -0.0011 | 0.5 in 100% of splits |
| SAM ViT-H NIR-blue-green | 0.1725 | 0.1736 | -0.0012 | 0.5 in 100% of splits |
| SAM ViT-H natural colour | 0.1669 | 0.1665 | +0.0004 | 0.5 in 100% of splits |
| SAM ViT-H colour infrared | 0.1831 | 0.1846 | -0.0015 | 0.5 in 100% of splits |

## Slovenia, what the methods emit

| method | objects/chip | no object | exactly one | 5 or more | matched share | parcels |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL | 19.5 | 53.3% | 39.4% | 0.1% | 42.06% | 6,831 |
| watershed 0.05 | 290.7 | 0.0% | 12.3% | 28.5% | 4.43% | 6,831 |

## Slovenia, held-out setting choice

| method | published | held out | optimism | setting |
|---|---:|---:|---:|---|
| watershed | 0.3484 | 0.3500 | -0.0016 | 0.05 in 100% of splits |
| felzenszwalb | 0.2137 | 0.2136 | +0.0001 | 100.0 in 100% of splits |
| SAM ViT-H blue-green-red | 0.2762 | 0.2717 | +0.0045 | 0.5 in 100% of splits |
| SAM ViT-H NIR-blue-green | 0.2486 | 0.2420 | +0.0066 | 0.5 in 100% of splits |
| SAM ViT-H natural colour | 0.2954 | 0.2934 | +0.0020 | 0.5 in 100% of splits |
| SAM ViT-H colour infrared | 0.2593 | 0.2612 | -0.0019 | 0.5 in 100% of splits |

## India, every method on the parcels the SAM subset covered

| method | parcels | objects/chip | no object | exactly one | 5 or more |
|---|---:|---:|---:|---:|---:|
| FTW 3-class FULL | 494 | 175.0 | 75.3% | 18.2% | 0.0% |
| SAM ViT-H colour infrared 0.50 | 494 | 195.6 | 10.1% | 30.0% | 8.9% |
| SAM ViT-H NIR-blue-green 0.50 | 494 | 190.4 | 8.7% | 33.0% | 8.5% |
| watershed 0.02 | 494 | 675.9 | 0.0% | 7.1% | 30.8% |

## Label registration


### Displacement, overall

| | India | Slovenia |
|---|---:|---:|
| parcels | 1,983 | 6,823 |
| pixel east to west | 6.087 m | 4.169 m |
| pixel north to south | 6.086 m | 5.998 m |
| signed mean displacement | +4.13 m | +3.80 m |
| median unsigned | 6.00 m | 6.00 m |
| median parcel width | 42.3 m | 30.4 m |
| median gain | 1.029x | 1.008x |
| peak on the drawn edge | 38.8% | 47.6% |
| same on a borrowed field | 13.1% | 14.9% |

### Displacement and recall at matched ground width

| ground width | India offset | India recall | Slovenia offset | Slovenia recall |
|---|---:|---:|---:|---:|
| under 20 m | +9.92 m | 0.00% | +5.92 m | 0.51% |
| 20 to 30 m | +6.64 m | 0.41% | +3.79 m | 7.89% |
| 30 to 50 m | +3.91 m | 0.58% | +2.71 m | 23.62% |
| 50 m up | +1.81 m | 7.11% | +2.23 m | 58.80% |

### Edge over the parcel's own interior

| | India | Slovenia |
|---|---:|---:|
| median | 1.297x | 1.588x |
| share at or below 1.0 | 14.2% | 7.2% |
| parcels wide enough | 1,467 | 4,307 |
| by width, 20 to 30 m | 1.118x | 1.257x |
| by width, 30 to 50 m | 1.236x | 1.441x |
| by width, 50 m up | 1.420x | 2.005x |

## Ring distance sensitivity


### India

| cap | ring left out | median area | median width | under 30 m | FTW 3-class FULL recall | watershed recall | felzenszwalb recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3 px, published | 0.17% | 0.323 ha | 42.3 m | 22.24% | 0.0272 | 0.2461 | 0.0842 |
| 12 m | 4.03% | 0.314 ha | 42.3 m | 22.29% | 0.0272 | 0.2471 | 0.0837 |
| 18 m | 0.21% | 0.323 ha | 42.3 m | 22.24% | 0.0272 | 0.2461 | 0.0837 |
| 24 m | 0.13% | 0.323 ha | 42.3 m | 22.24% | 0.0272 | 0.2461 | 0.0837 |

### Slovenia

| cap | ring left out | median area | median width | under 30 m | FTW 3-class FULL recall | watershed recall | felzenszwalb recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3 px, published | 1.07% | 0.315 ha | 30.4 m | 49.66% | 0.2222 | 0.3484 | 0.2137 |
| 12 m | 1.83% | 0.315 ha | 30.4 m | 49.76% | 0.2227 | 0.3467 | 0.2136 |
| 18 m | 0.89% | 0.317 ha | 30.4 m | 49.64% | 0.2222 | 0.3474 | 0.2137 |
| 24 m | 0.68% | 0.317 ha | 30.4 m | 49.61% | 0.2222 | 0.3474 | 0.2137 |

### SAM ViT-H 0.50, India, first 100 test chips

| cap | NIR-blue-green, first run recall | colour infrared recall |
|---|---:|---:|
| 3 px, published | 0.1619 (80/494) | 0.1599 (79/494) |
| 12 m | 0.1640 (81/494) | 0.1640 (81/494) |
| 18 m | 0.1619 (80/494) | 0.1619 (80/494) |
| 24 m | 0.1619 (80/494) | 0.1619 (80/494) |

### FTW at matched ground width, every cap

| cap | ground width | India | Slovenia | ratio |
|---|---|---:|---:|---:|
| 3 px, published | 20 to 30 m | 1/245, 0.41% | 97/1,229, 7.89% | 19.3x |
| 3 px, published | 30 to 50 m | 5/867, 0.58% | 411/1,740, 23.62% | 41.0x |
| 3 px, published | 50 m up | 48/675, 7.11% | 999/1,699, 58.80% | 8.3x |
| 12 m | 20 to 30 m | 1/228, 0.44% | 97/1,221, 7.94% | 18.1x |
| 12 m | 30 to 50 m | 5/867, 0.58% | 416/1,737, 23.95% | 41.5x |
| 12 m | 50 m up | 48/674, 7.12% | 998/1,695, 58.88% | 8.3x |
| 18 m | 20 to 30 m | 1/244, 0.41% | 97/1,224, 7.92% | 19.3x |
| 18 m | 30 to 50 m | 5/867, 0.58% | 415/1,745, 23.78% | 41.2x |
| 18 m | 50 m up | 48/675, 7.11% | 996/1,695, 58.76% | 8.3x |
| 24 m | 20 to 30 m | 1/245, 0.41% | 97/1,223, 7.93% | 19.4x |
| 24 m | 30 to 50 m | 5/867, 0.58% | 415/1,747, 23.76% | 41.2x |
| 24 m | 50 m up | 48/675, 7.11% | 996/1,695, 58.76% | 8.3x |

## Parcel shape

| method | India | Slovenia | Slovenia, India's widths | Slovenia, India's widths and shapes | ratio, widths | ratio, widths and shapes | share from shape | six-band check |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL | 2.72% | 22.22% | 31.37% | 29.03% | 11.52x | 10.66x | +0.03 [+0.01, +0.05] | +0.04 |
| watershed | 24.61% | 34.84% | 48.04% | 49.34% | 1.95x | 2.00x | -0.04 [-0.08, -0.01] | -0.04 |
| SAM ViT-H, blue-green-red | 15.63% | 27.62% | 37.97% | 39.69% | 2.43x | 2.54x | -0.05 [-0.09, -0.01] | -0.06 |
| SAM ViT-H natural colour | 16.69% | 29.54% | 40.63% | 42.05% | 2.43x | 2.52x | -0.04 [-0.08, -0.00] | -0.04 |

### Within each width band, Slovenia given India's shapes

| method | ground width | India | Slovenia | Slovenia, India's shapes | ratio | ratio after |
|---|---|---:|---:|---:|---:|---:|
| FTW 3-class FULL | under 20 m | 0/196, 0.00% | 0.51% | 0.18% | not readable | not readable |
| FTW 3-class FULL | 20 to 30 m | 1/245, 0.41% | 7.89% | 4.38% | 19.3x | 10.7x |
| FTW 3-class FULL | 30 to 50 m | 5/867, 0.58% | 23.62% | 18.41% | 41.0x | 31.9x |
| FTW 3-class FULL | 50 m up | 48/675, 7.11% | 58.80% | 60.00% | 8.3x | 8.4x |
| watershed | under 20 m | 2/196, 1.02% | 3.74% | 3.24% | 3.7x | 3.2x |
| watershed | 20 to 30 m | 12/245, 4.90% | 21.32% | 19.59% | 4.4x | 4.0x |
| watershed | 30 to 50 m | 195/867, 22.49% | 47.64% | 48.85% | 2.1x | 2.2x |
| watershed | 50 m up | 279/675, 41.33% | 71.10% | 74.15% | 1.7x | 1.8x |
| SAM ViT-H, blue-green-red | under 20 m | 1/196, 0.51% | 2.64% | 1.94% | 5.2x | 3.8x |
| SAM ViT-H, blue-green-red | 20 to 30 m | 5/245, 2.04% | 14.56% | 13.55% | 7.1x | 6.6x |
| SAM ViT-H, blue-green-red | 30 to 50 m | 76/867, 8.77% | 32.01% | 32.55% | 3.7x | 3.7x |
| SAM ViT-H, blue-green-red | 50 m up | 228/675, 33.78% | 64.39% | 69.30% | 1.9x | 2.1x |
| SAM ViT-H natural colour | under 20 m | 1/196, 0.51% | 2.82% | 1.99% | 5.5x | 3.9x |
| SAM ViT-H natural colour | 20 to 30 m | 4/245, 1.63% | 15.62% | 13.92% | 9.6x | 8.5x |
| SAM ViT-H natural colour | 30 to 50 m | 80/867, 9.23% | 34.48% | 35.12% | 3.7x | 3.8x |
| SAM ViT-H natural colour | 50 m up | 246/675, 36.44% | 68.57% | 72.78% | 1.9x | 2.0x |

## The two seasonal windows

### What each window shows

| country | window | dates | red, median | blue, median | blue, 95th percentile | NDVI, median | edge strength |
|---|---|---|---:|---:|---:|---:|---:|
| India | window_a | July to November 2016 | 1058 | 609 | 837 | 0.35 | 0.424 |
| India | window_b | March to June 2016 | 1652 | 901 | 1187 | 0.17 | 0.401 |
| Slovenia | window_a | May to August 2021 | 351 | 312 | 666 | 0.82 | 0.328 |
| Slovenia | window_b | September to October 2021 | 258 | 282 | 583 | 0.83 | 0.338 |

### FTW with its two windows rearranged

| what the model was given | India objects/chip | India recall | India null | Slovenia objects/chip | Slovenia recall | Slovenia null |
|---|---:|---:|---:|---:|---:|---:|
| shipped | 175.0 | 2.72% [1.72, 3.89] | 1.93% | 19.5 | 22.22% [18.52, 25.97] | 0.52% |
| swapped | 186.8 | 3.68% [2.48, 5.01] | 2.22% | 21.5 | 21.42% [17.98, 24.77] | 0.55% |
| a twice | 169.4 | 4.79% [3.39, 6.34] | 1.95% | 16.6 | 15.21% [11.95, 18.87] | 0.51% |
| b twice | 116.9 | 1.01% [0.50, 1.57] | 1.21% | 8.9 | 10.60% [7.69, 13.59] | 0.26% |

India: the shipped run differs from `pred_3class_full` on 1 pixel(s).

Slovenia: the shipped run differs from `pred_3class_full` on 3 pixel(s).

### The same, as a change from the shipped run, chip by chip

| what the model was given | India parcels gained | India parcels lost | India change | Slovenia parcels gained | Slovenia parcels lost | Slovenia change |
|---|---:|---:|---:|---:|---:|---:|
| swapped | 40 | 21 | +0.96 [+0.05, +1.92] | 285 | 340 | -0.81 [-1.97, +0.29] |
| a twice | 64 | 23 | +2.07 [+0.91, +3.27] | 207 | 686 | -7.01 [-8.51, -5.51] |
| b twice | 17 | 51 | -1.71 [-2.83, -0.61] | 98 | 892 | -11.62 [-13.60, -9.75] |

### FTW by ground width, each arrangement

| country | what the model was given | under 20 m | 20 to 30 m | 30 to 50 m | 50 m up |
|---|---|---:|---:|---:|---:|
| India | shipped | 0/196, 0.00% | 1/245, 0.41% | 5/867, 0.58% | 48/675, 7.11% |
| India | swapped | 0/196, 0.00% | 2/245, 0.82% | 6/867, 0.69% | 65/675, 9.63% |
| India | a twice | 0/196, 0.00% | 3/245, 1.22% | 16/867, 1.85% | 76/675, 11.26% |
| India | b twice | 0/196, 0.00% | 1/245, 0.41% | 5/867, 0.58% | 14/675, 2.07% |
| Slovenia | shipped | 11/2,163, 0.51% | 97/1,229, 7.89% | 411/1,740, 23.62% | 999/1,699, 58.80% |
| Slovenia | swapped | 13/2,163, 0.60% | 98/1,229, 7.97% | 403/1,740, 23.16% | 949/1,699, 55.86% |
| Slovenia | a twice | 7/2,163, 0.32% | 56/1,229, 4.56% | 266/1,740, 15.29% | 710/1,699, 41.79% |
| Slovenia | b twice | 4/2,163, 0.18% | 67/1,229, 5.45% | 227/1,740, 13.05% | 426/1,699, 25.07% |

### Watershed on each window, at FTW's object count

| gradient from | India, at 175 objects/chip | Slovenia, at 20 objects/chip |
|---|---:|---:|
| both windows stacked | 10.74% [8.98, 12.57] | 5.93% [5.00, 6.92] |
| window_a alone | 9.56% [7.97, 11.24] | 4.35% [3.64, 5.07] |
| window_b alone | 6.04% [4.76, 7.35] | 5.83% [4.99, 6.68] |

### Slovenia at FTW's budget, watershed measured

| method | recall at 20 objects/chip | how |
|---|---:|---|
| watershed | 0.059 | interpolated, sweep extended to h 0.6 in `season_test.py` |

## A December to February image

### FTW's own chips rebuilt from the archive

| chip | window | scene date | lowest band correlation | largest median difference |
|---|---|---|---:|---:|
| g0_0030 | window_a | 2016-11-25 | 0.9921 | 0.04% |
| g0_0030 | window_b | 2016-04-29 | 0.9945 | 0.07% |
| g0_0073 | window_a | 2016-07-15 | 0.9977 | 0.06% |
| g0_0073 | window_b | 2016-03-27 | 0.9976 | 0.00% |
| g0_0091 | window_a | 2016-11-12 | 0.9969 | 0.04% |
| g0_0091 | window_b | 2016-04-26 | 0.9975 | 0.11% |

### The December to February images

| season | chips | at or under 10% chip cloud | December | January | February |
|---|---:|---:|---:|---:|---:|
| 2016-17 | 399 | 399 | 177 | 40 | 182 |
| 2015-16 | 399 | 350 | 97 | 148 | 105 |

### FTW given the rabi image

| what the model was given | 2016-17 objects/chip | 2016-17 recall | 2016-17 null | 2015-16 objects/chip | 2015-16 recall | 2015-16 null |
|---|---:|---:|---:|---:|---:|---:|
| shipped, b then a | 175.0 | 2.72% | 1.98% | 175.9 | 2.70% | 2.05% |
| a twice | 169.4 | 4.79% | 2.03% | 175.0 | 5.35% | 2.09% |
| rabi for b, r then a | 197.9 | 4.74% | 2.39% | 197.5 | 4.03% | 2.22% |
| a then rabi | 209.9 | 5.50% | 2.59% | 214.4 | 4.66% | 2.44% |
| rabi twice | 117.8 | 2.27% | 1.48% | 114.9 | 1.09% | 1.19% |

2016-17: 398 labelled chips, 1,983 parcels.
2015-16: 349 labelled chips, 1,738 parcels.

### Watershed on the rabi image, at 175 objects per chip

| gradient from | 2016-17 | 2015-16 |
|---|---:|---:|
| b and a, as published | 10.74% | 11.23% |
| a alone | 9.56% | 10.14% |
| r alone | 10.08% | 9.81% |
| a and r | 11.19% | 13.07% |

### The changes, chip by chip

| method | comparison | 2016-17 | 2015-16 |
|---|---|---:|---:|
| FTW | rabi for b against shipped | +2.02 [+1.06, +2.98] | +1.32 [+0.40, +2.30] |
| FTW | rabi for b against a twice | -0.05 [-1.32, +1.21] | -1.32 [-2.76, +0.12] |
| FTW | a then rabi against shipped | +2.77 [+1.61, +3.93] | +1.96 [+1.03, +3.00] |
| FTW | rabi twice against shipped | -0.45 [-1.56, +0.65] | -1.61 [-2.81, -0.46] |
| FTW | a twice against shipped | +2.07 [+0.91, +3.27] | +2.65 [+1.50, +3.90] |
| watershed | r alone against a alone | +0.52 [-0.98, +1.96] | -0.33 [-2.25, +1.61] |
| watershed | a and r against b and a | +0.45 [-1.11, +1.93] | +1.84 [+0.20, +3.50] |
| watershed | a and r against a alone | +1.62 [+0.39, +2.89] | +2.93 [+1.35, +4.57] |

## FTW's later checkpoints

### Every checkpoint on both countries

| checkpoint | licence | India objects/chip | India recall | India null | Slovenia objects/chip | Slovenia recall | Slovenia null | India over Slovenia |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| v1 full | mixed | 175.0 | 2.72% [1.76, 3.88] | 2.15% | 19.5 | 22.22% [18.62, 25.99] | 0.56% | 0.122 [0.077, 0.178] |
| v1 cc-by | CC-BY | 84.0 | 2.98% [1.97, 4.10] | 0.72% | 13.4 | 14.46% [11.26, 17.41] | 0.37% | 0.206 [0.132, 0.305] |
| v2 full | mixed | 76.3 | 1.71% [1.06, 2.58] | 0.71% | 18.2 | 19.27% [16.03, 22.35] | 0.60% | 0.089 [0.053, 0.139] |
| v3 full b3 | mixed | 223.3 | 10.29% [8.51, 12.30] | 2.69% | 19.3 | 28.78% [24.98, 32.42] | 0.63% | 0.357 [0.285, 0.454] |
| v3 full b7 | mixed | 245.3 | 12.91% [10.66, 15.08] | 2.50% | 20.5 | 33.06% [29.00, 36.73] | 0.58% | 0.391 [0.316, 0.478] |
| v3.1 cc-by b3 | CC-BY | 154.7 | 8.22% [6.60, 9.92] | 1.34% | 12.1 | 16.81% [13.36, 20.10] | 0.32% | 0.489 [0.369, 0.656] |
| v3.1 cc-by b7 | CC-BY | 224.6 | 11.40% [9.38, 13.41] | 2.17% | 15.2 | 22.44% [18.55, 26.12] | 0.39% | 0.508 [0.397, 0.651] |

398 labelled Indian chips and 185 Slovenian, 1,983 and 6,831 parcels.

### Changes against a reference, chip by chip

| country | checkpoint | against | recall change | change above null |
|---|---|---|---:|---:|
| India | v1 cc-by | v1 full | +0.25 [-0.91, +1.41] | +1.68 [+0.52, +2.85] |
| India | v2 full | v1 full | -1.01 [-1.91, -0.15] | +0.44 [-0.62, +1.39] |
| India | v3 full b3 | v1 full | +7.56 [+5.94, +9.23] | +7.03 [+5.41, +8.73] |
| India | v3 full b7 | v1 full | +10.19 [+8.37, +12.15] | +9.83 [+7.93, +11.75] |
| India | v3.1 cc-by b3 | v1 full | +5.50 [+4.03, +7.12] | +6.30 [+4.79, +7.95] |
| India | v3.1 cc-by b7 | v1 full | +8.67 [+6.92, +10.54] | +8.66 [+6.76, +10.65] |
| India | v3.1 cc-by b3 | v1 cc-by | +5.24 [+3.93, +6.64] | +4.62 [+3.19, +6.11] |
| Slovenia | v1 cc-by | v1 full | -7.76 [-9.21, -6.28] | -7.57 [-9.15, -6.05] |
| Slovenia | v2 full | v1 full | -2.96 [-4.50, -1.35] | -3.00 [-4.58, -1.43] |
| Slovenia | v3 full b3 | v1 full | +6.56 [+4.73, +8.31] | +6.48 [+4.73, +8.12] |
| Slovenia | v3 full b7 | v1 full | +10.83 [+8.90, +12.56] | +10.81 [+8.91, +12.52] |
| Slovenia | v3.1 cc-by b3 | v1 full | -5.42 [-7.98, -2.93] | -5.18 [-7.94, -2.68] |
| Slovenia | v3.1 cc-by b7 | v1 full | +0.22 [-1.96, +2.11] | +0.39 [-1.80, +2.28] |
| Slovenia | v3.1 cc-by b3 | v1 cc-by | +2.34 [+0.13, +4.32] | +2.39 [+0.21, +4.30] |

### India, recall by ground width

| checkpoint | under 20 m | 20 to 30 m | 30 to 50 m | 50 m up |
|---|---:|---:|---:|---:|
| v1 full | 0.00% | 0.41% | 0.58% | 7.11% |
| v1 cc-by | 0.00% | 0.00% | 0.46% | 8.15% |
| v2 full | 0.00% | 0.00% | 0.23% | 4.74% |
| v3 full b3 | 1.02% | 0.82% | 3.34% | 25.33% |
| v3 full b7 | 0.00% | 1.22% | 4.96% | 31.11% |
| v3.1 cc-by b3 | 1.02% | 0.41% | 1.85% | 21.33% |
| v3.1 cc-by b7 | 0.00% | 0.82% | 3.92% | 28.15% |

Parcels per band: under 20 m 196, 20 to 30 m 245, 30 to 50 m 867, 50 m up 675.

### Slovenia, recall by ground width

| checkpoint | under 20 m | 20 to 30 m | 30 to 50 m | 50 m up |
|---|---:|---:|---:|---:|
| v1 full | 0.51% | 7.89% | 23.62% | 58.80% |
| v1 cc-by | 0.46% | 4.96% | 15.63% | 37.96% |
| v2 full | 0.23% | 4.48% | 18.79% | 54.68% |
| v3 full b3 | 2.27% | 14.48% | 34.48% | 67.04% |
| v3 full b7 | 3.61% | 20.26% | 40.98% | 71.69% |
| v3.1 cc-by b3 | 1.34% | 6.43% | 20.63% | 40.08% |
| v3.1 cc-by b7 | 2.13% | 13.51% | 27.13% | 49.97% |

Parcels per band: under 20 m 2,163, 20 to 30 m 1,229, 30 to 50 m 1,740, 50 m up 1,699.

## Watershed and SAM at the later checkpoints' budgets


### India

| checkpoint | objects/chip | FTW recall | method | read at | recall | minus FTW | reading |
|---|---:|---:|---|---:|---:|---:|---|
| v1 full | 175.0 | 2.72% | watershed | 175.0 | 10.74% | +8.01 [+6.28, +9.78] | method ahead |
| v1 full | 175.0 | 2.72% | SAM colour infrared | 175.0 | 15.78% | +13.05 [+10.99, +15.26] | method ahead |
| v1 full | 175.0 | 2.72% | SAM NIR-blue-green | 175.0 | 15.34% | +12.62 [+10.56, +14.66] | method ahead |
| v1 full | 175.0 | 2.72% | SAM natural colour | 175.0 | 15.17% | +12.44 [+10.40, +14.57] | method ahead |
| v1 full | 175.0 | 2.72% | SAM blue-green-red | 175.0 | 15.11% | +12.39 [+10.47, +14.48] | method ahead |
| v3 full b3 | 223.3 | 10.29% | watershed | 223.3 | 13.71% | +3.43 [+1.83, +4.98] | method ahead |
| v3 full b3 | 223.3 | 10.29% | SAM colour infrared | 222.4 | 18.31% | +8.02 [+6.03, +9.85] | method ahead, stands under P2 |
| v3 full b3 | 223.3 | 10.29% | SAM NIR-blue-green | 212.6 | 17.25% | +6.96 [+5.10, +8.86] | method ahead, stands under P2 |
| v3 full b3 | 223.3 | 10.29% | SAM natural colour | 194.6 | 16.69% | +6.40 [+4.53, +8.27] | method ahead, stands under P2 |
| v3 full b3 | 223.3 | 10.29% | SAM blue-green-red | 184.5 | 15.63% | +5.35 [+3.53, +7.22] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | watershed | 245.3 | 14.83% | +1.92 [+0.21, +3.59] | method ahead |
| v3 full b7 | 245.3 | 12.91% | SAM colour infrared | 222.4 | 18.31% | +5.40 [+3.38, +7.23] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | SAM NIR-blue-green | 212.6 | 17.25% | +4.34 [+2.42, +6.20] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | SAM natural colour | 194.6 | 16.69% | +3.78 [+1.97, +5.70] | method ahead, stands under P2 |
| v3 full b7 | 245.3 | 12.91% | SAM blue-green-red | 184.5 | 15.63% | +2.72 [+0.81, +4.59] | method ahead, stands under P2 |
| v3.1 cc-by b3 | 154.7 | 8.22% | watershed | 154.7 | 9.19% | +0.98 [-0.64, +2.66] | level |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM colour infrared | 155.3 | 14.52% | +6.30 [+4.60, +8.26] | unresolved under P2 |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM NIR-blue-green | 154.7 | 14.28% | +6.06 [+4.26, +7.74] | method ahead |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM natural colour | 154.7 | 14.03% | +5.81 [+4.03, +7.50] | method ahead |
| v3.1 cc-by b3 | 154.7 | 8.22% | SAM blue-green-red | 154.7 | 13.79% | +5.57 [+3.73, +7.42] | method ahead |
| v3.1 cc-by b7 | 224.6 | 11.40% | watershed | 224.6 | 13.78% | +2.39 [+0.75, +3.98] | method ahead |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM colour infrared | 222.4 | 18.31% | +6.91 [+5.09, +8.82] | method ahead, stands under P2 |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM NIR-blue-green | 212.6 | 17.25% | +5.85 [+3.95, +7.77] | method ahead, stands under P2 |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM natural colour | 194.6 | 16.69% | +5.30 [+3.43, +7.20] | method ahead, stands under P2 |
| v3.1 cc-by b7 | 224.6 | 11.40% | SAM blue-green-red | 184.5 | 15.63% | +4.24 [+2.32, +6.16] | method ahead, stands under P2 |

### Slovenia

| checkpoint | objects/chip | FTW recall | method | read at | recall | minus FTW | reading |
|---|---:|---:|---|---:|---:|---:|---|
| v1 full | 19.5 | 22.22% | watershed | 19.5 | 5.93% | -16.29 [-19.32, -13.16] | FTW ahead |
| v1 full | 19.5 | 22.22% | SAM colour infrared | 73.8 | 21.21% | -1.01 [-3.58, +1.50] | level |
| v1 full | 19.5 | 22.22% | SAM NIR-blue-green | 72.7 | 20.63% | -1.60 [-4.08, +0.83] | level |
| v1 full | 19.5 | 22.22% | SAM natural colour | 85.9 | 25.72% | +3.50 [+1.10, +5.93] | unresolved under P2 |
| v1 full | 19.5 | 22.22% | SAM blue-green-red | 78.8 | 23.38% | +1.16 [-1.31, +3.70] | level |
| v3 full b3 | 19.3 | 28.78% | watershed | 19.3 | 5.86% | -22.92 [-26.33, -19.60] | FTW ahead |
| v3 full b3 | 19.3 | 28.78% | SAM colour infrared | 73.8 | 21.21% | -7.57 [-10.17, -4.92] | FTW ahead, stands under P2 |
| v3 full b3 | 19.3 | 28.78% | SAM NIR-blue-green | 72.7 | 20.63% | -8.15 [-10.72, -5.58] | FTW ahead, stands under P2 |
| v3 full b3 | 19.3 | 28.78% | SAM natural colour | 85.9 | 25.72% | -3.06 [-5.40, -0.64] | FTW ahead, stands under P2 |
| v3 full b3 | 19.3 | 28.78% | SAM blue-green-red | 78.8 | 23.38% | -5.40 [-7.96, -2.90] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | watershed | 20.5 | 6.27% | -26.78 [-30.17, -23.22] | FTW ahead |
| v3 full b7 | 20.5 | 33.06% | SAM colour infrared | 73.8 | 21.21% | -11.84 [-14.51, -9.15] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | SAM NIR-blue-green | 72.7 | 20.63% | -12.43 [-15.09, -9.77] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | SAM natural colour | 85.9 | 25.72% | -7.33 [-9.93, -4.72] | FTW ahead, stands under P2 |
| v3 full b7 | 20.5 | 33.06% | SAM blue-green-red | 78.8 | 23.38% | -9.68 [-12.38, -6.80] | FTW ahead, stands under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | watershed | 12.1 | 3.44% | -13.37 [-16.57, -10.08] | FTW ahead |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM colour infrared | 73.8 | 21.21% | +4.41 [+1.48, +7.66] | unresolved under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM NIR-blue-green | 72.7 | 20.63% | +3.82 [+0.97, +6.64] | unresolved under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM natural colour | 85.9 | 25.72% | +8.92 [+6.31, +11.86] | unresolved under P2 |
| v3.1 cc-by b3 | 12.1 | 16.81% | SAM blue-green-red | 78.8 | 23.38% | +6.57 [+3.80, +9.73] | unresolved under P2 |
| v3.1 cc-by b7 | 15.2 | 22.44% | watershed | 15.2 | 4.49% | -17.95 [-21.28, -14.30] | FTW ahead |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM colour infrared | 73.8 | 21.21% | -1.23 [-4.03, +1.89] | level |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM NIR-blue-green | 72.7 | 20.63% | -1.82 [-4.63, +0.96] | level |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM natural colour | 85.9 | 25.72% | +3.28 [+0.40, +6.00] | unresolved under P2 |
| v3.1 cc-by b7 | 15.2 | 22.44% | SAM blue-green-red | 78.8 | 23.38% | +0.94 [-1.88, +4.02] | level |

## Edge contrast, tested on Slovenia

### Calibration, 60 Slovenian chips never scored

| blur, m | parcels | median edge over interior |
|---:|---:|---:|
| 0 | 1,646 | 1.6347 |
| 2 | 1,646 | 1.6291 |
| 4 | 1,646 | 1.5816 |
| 6 | 1,646 | 1.5247 |
| 8 | 1,646 | 1.4681 |
| 10 | 1,646 | 1.4020 |
| 12 | 1,646 | 1.3473 |
| 15 | 1,646 | 1.2870 |
| 18 | 1,646 | 1.2321 |
| 24 | 1,646 | 1.1463 |

Chosen blur: 14.5 m, where the median meets India's 1.297.

### The share of the gap closed, 125 scoring chips

| method | band | Slovenia | blurred | India | share closed | reading |
|---|---|---:|---:|---:|---:|---|
| FTW v3 B7 | 20 to 30 m | 16.64% | 5.82% | 1.22% | 0.702 [0.593, 0.815] |  |
| FTW v3 B7 | 30 to 50 m | 38.34% | 17.52% | 4.96% | 0.624 [0.559, 0.693] |  |
| FTW v3 B7 | 50 m up | 69.32% | 49.66% | 31.11% | 0.514 [0.437, 0.607] |  |
| FTW v3 B7 | 20 m up | 43.95% | 26.09% | 13.41% | 0.585 [0.523, 0.666] | credible main cause |
| watershed | 20 to 30 m | 19.22% | 6.90% | 4.90% | 0.860 [0.718, 1.010] |  |
| watershed | 30 to 50 m | 45.31% | 20.29% | 22.49% | 1.097 [0.984, 1.225] |  |
| watershed | 50 m up | 69.13% | 55.90% | 41.33% | 0.476 [0.385, 0.566] |  |
| watershed | 20 m up | 47.23% | 29.68% | 24.78% | 0.782 [0.691, 0.890] | credible main cause |
| watershed, matched objects | 20 to 30 m | 19.22% | 10.77% | 4.90% | 0.590 [0.447, 0.723] |  |
| watershed, matched objects | 30 to 50 m | 45.31% | 28.07% | 22.49% | 0.755 [0.654, 0.861] |  |
| watershed, matched objects | 50 m up | 69.13% | 57.36% | 41.33% | 0.423 [0.308, 0.531] |  |
| watershed, matched objects | 20 m up | 47.23% | 34.20% | 24.78% | 0.581 [0.498, 0.665] | credible main cause |

## The contrast measure against two people, India

### Rank score of the measure against each judge

| judge | parcels | n | marked visible | rank score | permutation p | reading |
|---|---|---:|---:|---:|---:|---|
| second person | all 60 | 60 | 29 | 0.742 | 0.0004 | weak |
| second person | panel 20260925 | 20 | 9 | 0.606 | 0.2309 | weak |
| second person | panel 20261012 | 20 | 11 | 0.788 | 0.0155 | tracks what a person sees |
| second person | new 20 | 20 | 9 | 0.808 | 0.0098 | tracks what a person sees |
| author | all 60 | 60 | 25 | 0.664 | 0.0150 | weak |
| author | panel 20260925 | 20 | 6 | 0.655 | 0.1572 | weak |
| author | panel 20261012 | 20 | 10 | 0.650 | 0.1449 | weak |
| author | new 20 | 20 | 9 | 0.707 | 0.0668 | weak |

### Agreement between the two judges

| parcels | n | both visible | both not | second only | author only | agree | kappa |
|---|---:|---:|---:|---:|---:|---:|---:|
| all 60 | 60 | 22 | 28 | 7 | 3 | 0.83 | 0.67 |
| panel 20260925 | 20 | 6 | 11 | 3 | 0 | 0.85 | 0.69 |
| panel 20261012 | 20 | 8 | 7 | 3 | 2 | 0.75 | 0.50 |
| new 20 | 20 | 8 | 10 | 1 | 1 | 0.90 | 0.80 |

## v3 B7 fine-tuned on India

### Val recall per epoch, on Kaggle

| epoch | India arm, India val | India arm, Slovenia val | mixed arm, India val | mixed arm, Slovenia val |
|---:|---:|---:|---:|---:|
| 0 | 12.02% | 35.10% | 12.02% | 35.10% |
| 1 | 14.84% | 25.79% | 14.71% | 35.47% |
| 2 | 14.51% | 20.09% | 15.25% | 34.81% |
| 3 | 14.91% | 21.04% | 13.83% | 36.26% |
| 4 | 16.05% | 20.44% | 12.63% | 35.10% |
| 5 | 17.19% | 20.40% | 13.57% | 36.00% |
| 6 | 15.85% | 18.97% | 15.38% | 36.60% |
| 7 | 15.85% | 19.61% | 12.02% | 35.58% |
| 8 | 17.46% | 19.41% | 15.72% | 36.99% |
| 9 | 17.53% | 20.54% | 12.83% | 36.57% |
| 10 | 15.72% | 21.21% | 12.89% | 35.75% |
| 11 | 17.26% | 19.94% | 14.64% | 36.78% |
| 12 | 17.73% | 20.22% | 15.51% | 36.24% |
| 13 | 18.33% | 19.44% | 11.89% | 35.83% |
| 14 | 18.00% | 17.76% | 12.22% | 35.24% |
| 15 | 17.46% | 19.17% | 13.63% | 35.53% |
| 16 | 17.73% | 18.56% | 13.36% | 37.48% |
| 17 | 17.53% | 17.30% | 13.16% | 36.19% |
| 18 | 15.78% | 17.44% | 15.38% | 37.12% |
| 19 | 17.19% | 16.29% | 13.43% | 36.39% |
| 20 | 17.80% | 17.47% | 13.23% | 35.27% |

### Test chips

| country | checkpoint | objects per chip | recall | interval | null | above null |
|---|---|---:|---:|---:|---:|---:|
| india | v3 full b7 | 245.3 | 12.91% | [10.84, 15.27] | 2.50% | 10.41% |
| india | v3 b7 ft india | 108.8 | 15.13% | [12.93, 17.47] | 0.71% | 14.42% |
| india | v3 b7 ft india+slovenia | 141.1 | 13.57% | [11.39, 15.79] | 1.13% | 12.44% |
| slovenia | v3 full b7 | 20.5 | 33.06% | [29.15, 36.64] | 0.58% | 32.48% |
| slovenia | v3 b7 ft india | 47.8 | 19.48% | [16.91, 21.92] | 0.90% | 18.59% |
| slovenia | v3 b7 ft india+slovenia | 23.0 | 35.18% | [31.36, 38.81] | 0.67% | 34.51% |

### Readings against v3 full B7

| test | checkpoint | difference | interval | reading |
|---|---|---:|---:|---|
| T1 India recall minus v3 | v3 b7 ft india | +2.22 | [+0.86, +3.63] | helps on India, from better placed boundaries |
| T2 India above null minus v3 | v3 b7 ft india | +4.02 | [+2.62, +5.41] |  |
| T4 India over Slovenia minus v3 | v3 b7 ft india | 0.386 | [0.293, 0.489] |  |
| T5 Slovenia recall minus v3 | v3 b7 ft india | -13.57 | [-15.46, -11.64] |  |
| T1 India recall minus v3 | v3 b7 ft india+slovenia | +0.66 | [-0.60, +1.91] | no gain on India |
| T2 India above null minus v3 | v3 b7 ft india+slovenia | +2.03 | [+0.69, +3.31] |  |
| T4 India over Slovenia minus v3 | v3 b7 ft india+slovenia | -0.005 | [-0.046, 0.033] |  |
| T5 Slovenia recall minus v3 | v3 b7 ft india+slovenia | +2.12 | [+1.16, +3.33] |  |

### Watershed at each checkpoint's object count

| country | checkpoint | objects per chip | FTW | watershed | watershed minus FTW | interval | reading |
|---|---|---:|---:|---:|---:|---:|---|
| india | v3 full b7 | 245.3 | 12.91% | 14.83% | +1.92 | [+0.20, +3.60] | method ahead |
| india | v3 b7 ft india | 108.8 | 15.13% | 5.71% | -9.42 | [-11.43, -7.41] | FTW ahead |
| india | v3 b7 ft india+slovenia | 141.1 | 13.57% | 8.16% | -5.40 | [-7.27, -3.53] | FTW ahead |
| slovenia | v3 full b7 | 20.5 | 33.06% | 6.27% | -26.78 | [-30.09, -23.24] | FTW ahead |
| slovenia | v3 b7 ft india | 47.8 | 19.48% | 14.88% | -4.60 | [-6.72, -2.51] | FTW ahead |
| slovenia | v3 b7 ft india+slovenia | 23.0 | 35.18% | 7.11% | -28.07 | [-31.17, -24.72] | FTW ahead |

### SAM at each checkpoint's object count, added after the result

| country | checkpoint | objects per chip | FTW | method | read at | recall | minus FTW | interval | reading |
|---|---|---:|---:|---|---:|---:|---:|---:|---|
| india | v3 full b7 | 245.3 | 12.91% | SAM colour infrared | 222.4 | 18.31% | +5.40 | [+3.53, +7.26] | method ahead, stands under P2 |
| india | v3 full b7 | 245.3 | 12.91% | SAM NIR-blue-green | 212.6 | 17.25% | +4.34 | [+2.42, +6.23] | method ahead, stands under P2 |
| india | v3 full b7 | 245.3 | 12.91% | SAM natural colour | 194.6 | 16.69% | +3.78 | [+1.97, +5.65] | method ahead, stands under P2 |
| india | v3 full b7 | 245.3 | 12.91% | SAM blue-green-red | 184.5 | 15.63% | +2.72 | [+0.86, +4.70] | method ahead, stands under P2 |
| india | v3 b7 ft india | 108.8 | 15.13% | SAM colour infrared | 155.3 | 14.52% | -0.61 | [-2.52, +1.46] | level |
| india | v3 b7 ft india | 108.8 | 15.13% | SAM NIR-blue-green | 146.8 | 13.87% | -1.26 | [-3.22, +0.71] | level |
| india | v3 b7 ft india | 108.8 | 15.13% | SAM natural colour | 135.4 | 12.96% | -2.17 | [-4.13, -0.10] | FTW ahead, stands under P2 |
| india | v3 b7 ft india | 108.8 | 15.13% | SAM blue-green-red | 128.7 | 12.15% | -2.98 | [-4.94, -1.01] | FTW ahead, stands under P2 |
| india | v3 b7 ft india+slovenia | 141.1 | 13.57% | SAM colour infrared | 155.3 | 14.52% | +0.96 | [-0.86, +2.82] | level |
| india | v3 b7 ft india+slovenia | 141.1 | 13.57% | SAM NIR-blue-green | 146.8 | 13.87% | +0.30 | [-1.56, +2.07] | level |
| india | v3 b7 ft india+slovenia | 141.1 | 13.57% | SAM natural colour | 141.1 | 13.28% | -0.29 | [-2.13, +1.52] | level |
| india | v3 b7 ft india+slovenia | 141.1 | 13.57% | SAM blue-green-red | 141.1 | 12.93% | -0.63 | [-2.43, +1.21] | level |
| slovenia | v3 full b7 | 20.5 | 33.06% | SAM colour infrared | 73.8 | 21.21% | -11.84 | [-14.62, -9.17] | FTW ahead, stands under P2 |
| slovenia | v3 full b7 | 20.5 | 33.06% | SAM NIR-blue-green | 72.7 | 20.63% | -12.43 | [-15.15, -9.84] | FTW ahead, stands under P2 |
| slovenia | v3 full b7 | 20.5 | 33.06% | SAM natural colour | 85.9 | 25.72% | -7.33 | [-9.98, -4.87] | FTW ahead, stands under P2 |
| slovenia | v3 full b7 | 20.5 | 33.06% | SAM blue-green-red | 78.8 | 23.38% | -9.68 | [-12.35, -7.00] | FTW ahead, stands under P2 |
| slovenia | v3 b7 ft india | 47.8 | 19.48% | SAM colour infrared | 73.8 | 21.21% | +1.73 | [-0.15, +3.56] | level |
| slovenia | v3 b7 ft india | 47.8 | 19.48% | SAM NIR-blue-green | 72.7 | 20.63% | +1.14 | [-0.72, +3.13] | level |
| slovenia | v3 b7 ft india | 47.8 | 19.48% | SAM natural colour | 85.9 | 25.72% | +6.24 | [+4.51, +7.99] | unresolved under P2 |
| slovenia | v3 b7 ft india | 47.8 | 19.48% | SAM blue-green-red | 78.8 | 23.38% | +3.89 | [+2.08, +5.73] | unresolved under P2 |
| slovenia | v3 b7 ft india+slovenia | 23.0 | 35.18% | SAM colour infrared | 73.8 | 21.21% | -13.97 | [-16.59, -11.37] | FTW ahead, stands under P2 |
| slovenia | v3 b7 ft india+slovenia | 23.0 | 35.18% | SAM NIR-blue-green | 72.7 | 20.63% | -14.55 | [-17.18, -11.94] | FTW ahead, stands under P2 |
| slovenia | v3 b7 ft india+slovenia | 23.0 | 35.18% | SAM natural colour | 85.9 | 25.72% | -9.46 | [-12.00, -6.95] | FTW ahead, stands under P2 |
| slovenia | v3 b7 ft india+slovenia | 23.0 | 35.18% | SAM blue-green-red | 78.8 | 23.38% | -11.80 | [-14.44, -9.09] | FTW ahead, stands under P2 |

### Recall by ground width, description only

| country | checkpoint | band | parcels | recall |
|---|---|---|---:|---:|
| india | v3 full b7 | 20 to 30 m | 245 | 1.22% |
| india | v3 full b7 | 30 to 50 m | 867 | 4.96% |
| india | v3 full b7 | 50 m up | 675 | 31.11% |
| india | v3 b7 ft india | 20 to 30 m | 245 | 1.63% |
| india | v3 b7 ft india | 30 to 50 m | 867 | 7.50% |
| india | v3 b7 ft india | 50 m up | 675 | 34.07% |
| india | v3 b7 ft india+slovenia | 20 to 30 m | 245 | 0.41% |
| india | v3 b7 ft india+slovenia | 30 to 50 m | 867 | 6.46% |
| india | v3 b7 ft india+slovenia | 50 m up | 675 | 31.41% |
| slovenia | v3 full b7 | 20 to 30 m | 1,229 | 20.26% |
| slovenia | v3 full b7 | 30 to 50 m | 1,740 | 40.98% |
| slovenia | v3 full b7 | 50 m up | 1,699 | 71.69% |
| slovenia | v3 b7 ft india | 20 to 30 m | 1,229 | 7.49% |
| slovenia | v3 b7 ft india | 30 to 50 m | 1,740 | 20.80% |
| slovenia | v3 b7 ft india | 50 m up | 1,699 | 50.26% |
| slovenia | v3 b7 ft india+slovenia | 20 to 30 m | 1,229 | 23.03% |
| slovenia | v3 b7 ft india+slovenia | 30 to 50 m | 1,740 | 44.25% |
| slovenia | v3 b7 ft india+slovenia | 50 m up | 1,699 | 74.57% |
