import os
import ccxt.async_support as ccxt_async
import asyncio
import discord
import pandas as pd
from ta.momentum import RSIIndicator
import logging
import matplotlib.pyplot as plt
from io import BytesIO
import matplotlib.dates as mdates
import datetime

# Set up logging to a file
log_file = "app.log_1h"
logging.basicConfig(filename=log_file, level=logging.INFO)

# Initialize the Binance exchange API wrapper
exchange = ccxt_async.binance({'enableRateLimit': True})

# Initialize the Discord bot
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

# Define Discord channel IDs for different timeframes
CHANNELS = {
    '15m': 'XXXXXXXXXXXXXXX',
    '1h': 'XXXXXXXXXXXXXXXX',
    '4h': 'XXXXXXXXXXXXXXXXXX',
    '1d': 'XXXXXXXXXXXXXXXXX',
}

# Define RSI thresholds
overbought = 70
oversold = 30
extreme_overbought = 80
extreme_oversold = 20

# Define trading symbols to monitor
symbols = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'NEO/USDT', 'LTC/USDT', 'QTUM/USDT', 'ADA/USDT', 'XRP/USDT', 'EOS/USDT',
    'TUSD/USDT', 'IOTA/USDT', 'XLM/USDT', 'ONT/USDT', 'TRX/USDT', 'ETC/USDT', 'ICX/USDT', 'VEN/USDT', 'NULS/USDT',
    'VET/USDT', 'PAX/USDT', 'BCH/USDT', 'BSV/USDT', 'USDC/USDT', 'LINK/USDT', 'WAVES/USDT', 'BTT/USDT', 'USDS/USDT',
    'ONG/USDT', 'HOT/USDT', 'ZIL/USDT', 'ZRX/USDT', 'FET/USDT', 'BAT/USDT', 'XMR/USDT', "ZIL/USDT", 'ZRX/USDT',
    'FET/USDT', 'BAT/USDT', 'XMR/USDT'
]

# Define timeframes to monitor
timeframes = ["15m", "1h", "4h", "1d"]

# Function to fetch OHLCV data for a symbol and timeframe
async def fetch_ohlcv(symbol, timeframe, limit=None, max_retries=3):
    retries = 0
    while retries < max_retries:
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            logging.error(f"Error fetching data for {symbol} at {timeframe}: {e}")
            retries += 1
            await asyncio.sleep(2)

    print(f"Failed to fetch data for {symbol} at {timeframe} after {max_retries} retries")
    return pd.DataFrame()

# Function to calculate RSI for a DataFrame
def calculate_rsi(df, column_name="close", window=14):
    rsi = RSIIndicator(df[column_name], window)
    df["rsi"] = rsi.rsi()
    return df

# Event handler for when the Discord bot is ready
@client.event
async def on_ready():
    logging.info(f'{client.user} has connected to Discord!')
    await monitor_rsi()

# Function to monitor RSI for a specific symbol and timeframe
async def monitor_symbol(symbol, timeframe, previous_rsi_states):
    try:
        # Fetch OHLCV data
        df = await fetch_ohlcv(symbol, timeframe, limit=100) # Fetch the last 100 candles
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Get the current timestamp
        logging.info(f"Data for {symbol} fetched at {current_time}")
        df = calculate_rsi(df)
        current_rsi = df["rsi"].iloc[-1]  # get the last RSI value

        # Detect RSI signals for the most recent candle
        if extreme_overbought > current_rsi >= overbought and previous_rsi_states.get((symbol, timeframe)) not in ["Overbought","Extreme_Overbought"]:
            await send_signal(symbol, timeframe, "Overbought", df)
            previous_rsi_states[(symbol, timeframe)] = "Overbought"
        elif current_rsi >= extreme_overbought and previous_rsi_states.get((symbol,timeframe)) != "Extreme_Overbought":
            await send_signal(symbol, timeframe, "Extreme_Overbought", df)
            previous_rsi_states[(symbol, timeframe)] = "Extreme_Overbought"
        elif extreme_overbought > current_rsi >= overbought and previous_rsi_states.get((symbol,timeframe)) not in ["Overbought","Neutral","Oversold","Extreme_Oversold"]:
            await send_signal(symbol, timeframe, "Overbought", df)
            previous_rsi_states[(symbol, timeframe)] = "Overbought"
        elif overbought > current_rsi > oversold and previous_rsi_states.get((symbol,timeframe)) not in ["Neutral","Oversold","Extreme_Oversold"]:
            await send_signal(symbol, timeframe, "Neutral", df)
            previous_rsi_states[(symbol, timeframe)] = "Neutral"
        elif oversold >= current_rsi > extreme_oversold and previous_rsi_states.get((symbol,timeframe)) not in ["Oversold","Extreme_Oversold"]:
            await send_signal(symbol, timeframe, "Oversold", df)
            previous_rsi_states[(symbol, timeframe)] = "Oversold"
        elif extreme_oversold >= current_rsi and previous_rsi_states.get((symbol,timeframe)) != "Extreme_Oversold":
            await send_signal(symbol, timeframe, "Extreme_Oversold", df)
            previous_rsi_states[(symbol, timeframe)] = "Extreme_Oversold"
        elif oversold > current_rsi > extreme_oversold and previous_rsi_states.get((symbol,timeframe)) not in ["Oversold","Neutral","Overbought","Extreme_Overbought"]:
            await send_signal(symbol, timeframe, "Oversold", df)
            previous_rsi_states[(symbol, timeframe)] = "Oversold"
        elif overbought > current_rsi >= oversold and previous_rsi_states.get((symbol,timeframe)) not in ["Neutral","Overbought","Extreme_Overbought"]:
            await send_signal(symbol, timeframe, "Neutral", df)
            previous_rsi_states[(symbol, timeframe)] = "Neutral"

    except Exception as e:
        logging.error(f"Error monitoring {symbol} at {timeframe}: {e}")

# Function to continuously monitor RSI for all symbols
async def monitor_rsi():
    previous_rsi_states = {}  # to store the last RSI state

    while True:  # keep running indefinitely
        tasks = []
        for symbol in symbols:
            timeframe = "1h"
            task = asyncio.ensure_future(monitor_symbol(symbol, timeframe, previous_rsi_states))
            tasks.append(task)

        await asyncio.gather(*tasks)
        await asyncio.sleep(3600)  # wait for a minute (or adjust as needed) before checking again

# Function to send an RSI signal message to Discord
async def send_signal(symbol, timeframe, signal, df):
    try:
        # Look up the channel ID for the given timeframe
        channel_id = CHANNELS.get(timeframe)
        if channel_id is None:
            logging.error(f"No Discord channel configured for timeframe: {timeframe}")
            return

        # Get the Discord channel object
        channel = client.get_channel(int(channel_id))

        # Create a new figure and set its size
        plt.figure(figsize=(12, 8))

        # Generate the Symbol Price Graph
        # Generate the Symbol Price Graph
        plt.subplot(2, 1, 1)
        plt.plot(df['close'])
        plt.title(f'{symbol} Price Chart', fontsize=14)
        plt.xlabel('Time (Month,Day,Hour)', fontsize=12)
        plt.ylabel('Price', fontsize=12)

        # Generate the RSI Graph
        plt.subplot(2, 1, 2)
        plt.plot(df['rsi'])
        plt.axhline(y=overbought, color='r', linestyle='--')
        plt.axhline(y=oversold, color='r', linestyle='--')
        plt.axhline(y=extreme_overbought, color='r', linestyle='--')
        plt.axhline(y=extreme_oversold, color='r', linestyle='--')
        plt.title('RSI Graph', fontsize=14)
        plt.xlabel('Time (Month,Day,Hour)', fontsize=12)
        plt.ylabel('RSI Value', fontsize=12)

        # Adjust the spacing between the subplots
        plt.tight_layout(pad=4.0)



        # Save the figure to a BytesIO object
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        # Send the image file in Discord message
        await asyncio.sleep(2)  # sleep for 2 seconds before sending the message
        while True:
            try:
                await channel.send(f"@everyone For {symbol} at {timeframe}, the RSI indicates **{signal}**!",
                                   file=discord.File(buffer, 'rsi_chart.png'))
                break  # exit the loop if the message was sent successfully
            except discord.HTTPException as e:
                if e.status == 429:
                    # wait the amount of time that Discord tells us to wait
                    await asyncio.sleep(e.retry_after)
                else:
                    raise  # re-raise the exception if it's not a rate limit exception

        # Close the current figure
        plt.close()
    except Exception as e:
        logging.error(f"Error sending signal for {symbol} at {timeframe}: {e}")

token = "XXXXXXXXXXXXXXXX"

async def main():
    try:
        await client.start(token)
    finally:
        await client.close()
        await exchange.close()

asyncio.run(main())
