# Uniswap v3 Active Strategy Framework and Simulator

![Banner](https://user-images.githubusercontent.com/80003108/127793159-abdcfad8-4e74-4554-8427-24b5569898ec.png)

## Introduction

This repository contains several python scripts that are used by [Gamma Strategies](https://medium.com/gamma-strategies) to simulate the performance of Uniswap v3 liquidity provision strategies' performance and evaluate risks. The main scripts of the package are:

1. ```StrategyImplementer.py``` which performs the simulations and extracts the statistics necesary for analysis. This file can be modified to implement any LP strategy, and it will be simulated with this code.
2. ```GetPoolData.py``` which downloads the data necessary for the simulations from Bitquery and Flipside
3. ```UNI_v3_funcs.py``` which is a slightly modified version of [JNP777's](https://github.com/JNP777/UNI_V3-Liquitidy-amounts-calcs) Python implementation of Uniswap v3's [liquidity math](https://github.com/Uniswap/uniswap-v3-periphery/blob/main/contracts/libraries/LiquidityAmounts.sol). 

In order to show usage, we have included a Jupyter Notebook ```Strategy_simlation_example.ipynb``` which runs an example 'reset strategy' in the spirit of the work reviewed in this [Gamma Strategies article](https://medium.com/gamma-strategies/expected-price-range-strategies-in-uniswap-v3-833dff253f84). 

We have constructed a flexible framework for active LP strategy simulations that use **the full Uniswap v3 swap history** in order to improve accurracy. Thefore simulations are available in the time period since Unsiwap v3 was released (May 5 2021 is when swap data starts to show up consistently). 


## Simulating your own strategy

In order to simulate your own strategy you should clone this repository to your local computer, and implement your algorithm in the ```StrategyImplementer.py``` script. This script implements a ```StrategyObvservation``` object that for each time period stores the state of the strategy, accumulated fees and all relevant variables, as well as performing the rebalancing logic.

The template is currently adapted to the strategies used by [Visor Finance's Hypervisor](https://github.com/VisorFinance/hypervisor), which set a base liquidity provision position, and a limit one with the tokens that are left over as may occur due to concentrated liquidity math and single sided deposits, but this could be generalized as well.

You will then modify the following functions:

1. ```set_liquidity_ranges``` computes where the LP ranges are set in an LP strategy and stores the virtual liquidity placed for each position. 
2. ```check_strategy``` to implement your algorithm's rebalancing logic.

To update the data vs. the one stored in this repo you will need to sign up at [Bitquery](https://graphql.bitquery.io/ide) and save your API key in a file called ```config.py``` in this directory, as a string: ```BITQUERY_API_TOKEN = XXXXXXXX```, and set ```DOWNLOAD_DATA      = True``` in the notebook. You can debug by looking at the ```strategy.log``` output file which prints details at each rebalance.

## Simulate With Any Uniswap v3 Pair

The current implementation is very flexible, but due to data constraints is currently programmed to analyze the WETH-USDC 0.3% fee tier pool. If you want to generate this for a different pool, you must generate a new FlipsideCrypto query like the one [from this example](https://app.flipsidecrypto.com/velocity/queries/b8ad3087-803a-478b-9ed3-c4f3c096bc47), with the ```pool_address``` for the pair that you are interested in and modify the ```get_liquidity_flipside``` function from ```GetPoolData```.

## Potential Sources of inaccurracy

There are several potential sources for imprecision, as for example gas fees are not taken into account, and can have a significant impact on performance in particular for small positions in high fee regimes. There could be rounding issues from the Python implementation of the Solidity code, and price differences from the pool price due to Bitquery's price feed not being identical to that of the pool (as expected).
