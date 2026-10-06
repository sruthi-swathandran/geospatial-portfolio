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
| SAM ViT-H true colour | 0.50/0.88 | 117 | 0.194 | 0.276 | 0.013 | +0.264 |
| SAM ViT-H true colour | 0.60/0.88 | 117 | 0.194 | 0.276 | 0.014 | +0.262 |
| SAM ViT-H true colour | 0.70/0.88 | 115 | 0.190 | 0.274 | 0.012 | +0.262 |
| SAM ViT-H true colour | 0.80/0.88 | 109 | 0.173 | 0.264 | 0.012 | +0.252 |
| SAM ViT-H true colour | 0.88/0.88 | 89 | 0.119 | 0.234 | 0.010 | +0.224 |
| SAM ViT-H false colour | 0.50/0.88 | 116 | 0.155 | 0.249 | 0.014 | +0.235 |
| SAM ViT-H false colour | 0.60/0.88 | 116 | 0.155 | 0.248 | 0.012 | +0.237 |
| SAM ViT-H false colour | 0.70/0.88 | 114 | 0.151 | 0.246 | 0.013 | +0.234 |
| SAM ViT-H false colour | 0.80/0.88 | 106 | 0.130 | 0.236 | 0.013 | +0.223 |
| SAM ViT-H false colour | 0.88/0.88 | 85 | 0.085 | 0.206 | 0.010 | +0.196 |

## Slovenia, at FTW's object budget

| method | recall at 20 objects/chip | null | gap | how |
|---|---:|---:|---:|---|
| FTW 3-class FULL | 0.222 | 0.007 | +0.215 | single setting |
| watershed | 0.081 | 0.003 | +0.078 | clamped, sweep stops at 26 objects |
| felzenszwalb | 0.037 | 0.006 | +0.030 | clamped, sweep stops at 65 objects |
| SAM ViT-H true colour | 0.234 | 0.010 | +0.224 | clamped, sweep stops at 89 objects |
| SAM ViT-H false colour | 0.206 | 0.010 | +0.196 | clamped, sweep stops at 85 objects |

## Slovenia, recall by ground width

SAM at threshold 0.50, classical methods at their best setting.

| ground width | parcels | FTW 3-class FULL | watershed | SAM ViT-H true colour | SAM ViT-H false colour |
|---|---:|---:|---:|---:|---:|
| under 20 m | 2,163 | 0.51% | 3.74% | 2.64% | 1.62% |
| 20 to 30 m | 1,229 | 7.89% | 21.32% | 14.56% | 12.12% |
| 30 to 50 m | 1,740 | 23.62% | 47.64% | 32.01% | 27.76% |
| 50 m up | 1,699 | 58.80% | 71.10% | 64.39% | 60.68% |

## Slovenia, the same widths cut finer

SAM at threshold 0.50, classical methods at their best setting.

| width, native 10 m px | parcels | FTW 3-class FULL | watershed | SAM ViT-H true colour | SAM ViT-H false colour |
|---|---:|---:|---:|---:|---:|
| under 2 | 2,163 | 0.51% | 3.74% | 2.64% | 1.62% |
| 2 to 3 | 1,229 | 7.89% | 21.32% | 14.56% | 12.12% |
| 3 to 4 | 1,193 | 18.86% | 42.92% | 27.75% | 24.14% |
| 4 to 5 | 547 | 34.00% | 57.95% | 41.32% | 35.65% |
| 5 to 7 | 827 | 48.49% | 68.80% | 55.86% | 50.67% |
| 7 to 10 | 553 | 66.18% | 75.23% | 69.80% | 67.09% |
| 10 and over | 319 | 72.73% | 69.91% | 77.12% | 75.55% |

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
| under 20 m | SAM ViT-H true colour | 1/196, 0.51% | 57/2,163, 2.64% | 5.2x |
| 20 to 30 m | SAM ViT-H true colour | 5/245, 2.04% | 179/1,229, 14.56% | 7.1x |
| 30 to 50 m | SAM ViT-H true colour | 76/867, 8.77% | 557/1,740, 32.01% | 3.7x |
| 50 m up | SAM ViT-H true colour | 228/675, 33.78% | 1094/1,699, 64.39% | 1.9x |

## India, what the methods emit

| method | objects/chip | no object | exactly one | 5 or more | matched share | parcels |
|---|---:|---:|---:|---:|---:|---:|
| FTW 3-class FULL | 175.0 | 74.4% | 18.9% | 0.3% | 0.08% | 1,983 |
| SAM ViT-H false 0.50 (subset) | 190.4 | 8.7% | 33.0% | 8.5% | 0.42% | 494 |
| watershed 0.02 | 675.9 | 0.0% | 7.2% | 38.2% | 0.18% | 1,983 |

## India, held-out setting choice

| method | published | held out | optimism | setting |
|---|---:|---:|---:|---|
| watershed | 0.2461 | 0.2444 | +0.0016 | 0.02 in 62% of splits |
| felzenszwalb | 0.0842 | 0.0848 | -0.0005 | 100.0 in 100% of splits |
| sam_vit_h_true | 0.1563 | 0.1574 | -0.0011 | 0.5 in 100% of splits |
| sam_vit_h_false | 0.1725 | 0.1736 | -0.0012 | 0.5 in 100% of splits |

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
| sam_vit_h_true | 0.2762 | 0.2717 | +0.0045 | 0.5 in 100% of splits |
| sam_vit_h_false | 0.2486 | 0.2420 | +0.0066 | 0.5 in 100% of splits |

## India, every method on the parcels the SAM subset covered

| method | parcels | objects/chip | no object | exactly one | 5 or more |
|---|---:|---:|---:|---:|---:|
| FTW 3-class FULL | 494 | 175.0 | 75.3% | 18.2% | 0.0% |
| SAM ViT-H false 0.50 | 494 | 190.4 | 8.7% | 33.0% | 8.5% |
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
