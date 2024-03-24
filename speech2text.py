import requests
import re

# from google.colab import drive
from moviepy.editor import *
import whisper
from langchain.llms import OpenAI
from googleapiclient.discovery import build
from google.oauth2 import service_account

# drive.mount('/content/drive')


def download_tiktok(url):
    querystring = {"url": url}

    headers = {
        "X-RapidAPI-Key": "7b0ea31ba2msh3cc78d4a4525496p189cc8jsn8fcbfd95ffc2",
        "X-RapidAPI-Host": "tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com",
    }

    response = requests.get(
        "https://tiktok-downloader-download-tiktok-videos-without-watermark.p.rapidapi.com/vid/index",
        headers=headers,
        params=querystring,
    )

    print(response.json())
    video_url = response.json()["video"][0]

    response = requests.get(video_url)

    if response.status_code == 200:
        with open("downloaded_video.mp4", "wb") as file:
            file.write(response.content)
        print("Video downloaded successfully.")
    else:
        print(f"Failed to download video. Status code: {response.status_code}")


def obtain_audio(file_path):

    # Replace 'your_video.mp4' with the path to your video file
    video = VideoFileClip(file_path)

    # Replace 'output_audio.mp3' with the desired output MP3 file name
    video.audio.write_audiofile("output_audio.wav")


def execute_transcription():
    # Load the model
    model = whisper.load_model("base")

    # Transcribe the audio
    result = model.transcribe("output_audio.wav")

    # Get the transcription text
    transcription = result["text"]
    print(transcription)
    return transcription


def execute_gpt(text):
    llm = OpenAI(api_key="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")

    transcribed_text = f"{text}"

    prompt = [
        f"Identify all restaurants/attractions mentioned in the following tiktok audio transcript with city, state, country they are located in: {transcribed_text}. If place name is unclear (ie. the text transcript says Booted In, but could instead be Boudin Bakery in San Francisco), try fixing it. provide what the transcript says was a recommended item. Provide your response in this strict format: 'Name: _, Location: _, Notes: _'"
    ]

    response = llm.generate(prompt)

    print(response)
    output = response.generations[0][0].text.strip()
    locations = output.split("\n")
    return locations


# Sheets API setup
SHEETS_SERVICE_ACCOUNT_FILE = "./googlesheets_pk.json"
SPREADSHEET_ID = "1UCq8qQIRUNBbtwAV4tZAUu-2sxPyNGeQaqgt9ODD8LY"
SHEET_NAME = "Sheet2"


def update_sheet(locations):
    rows_to_insert = []
    for location in locations:
        split_loc = location.split(", Location: ")
        name = split_loc[0].split("Name: ")[1]
        split_notes = split_loc[1].split(", Notes/Recommendations:")
        location = split_notes[0]
        notes = split_notes[1]
        rows_to_insert.append([name, location, notes])

    credentials = service_account.Credentials.from_service_account_file(
        SHEETS_SERVICE_ACCOUNT_FILE
    )
    service = build("sheets", "v4", credentials=credentials)

    request_body = {"values": rows_to_insert}
    response = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:D",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=request_body,
        )
        .execute()
    )

    print("Update Complete. Response:", response)


# !pip install -q streamlit

# %%writefile app.py

# import streamlit as st
# st.title("TikTok Video Location Extractor")

# # Input for TikTok video ID
# video_id = st.text_input("Enter TikTok Video ID:")
# if st.button("Process Video"):
#   if video_id:
#     download_tiktok(url)
#     obtain_audio("./downloaded_video.mp4")
#     text = execute_transcription()
#     locations = execute_gpt(text)
#     update_status = update_sheet(locations)
#     if update_status:
#       st.success("Google Sheet updated successfully.")
#     else:
#       st.error("Failed to update Google Sheet.")
#   else:
#     st.error("Please enter a valid TikTok Video ID.")

# !npm install localtunnel
# !streamlit run app.py &>/content/logs.txt &
# import urllib
# print("Password/Enpoint IP for localtunnel is:",urllib.request.urlopen('https://ipv4.icanhazip.com').read().decode('utf8').strip("\n"))
# !npx localtunnel --port 8501

# path = '/content/drive/My Drive/tiktok-gpt/tiktok1.mov'
# download_tiktok(url)
# obtain_audio("./downloaded_video.mp4")
# text = execute_transcription()
# locations = execute_gpt(text)
# update_sheet(locations)
import streamlit as st


def main():
    st.title("TikTok Video Processor")

    url = st.text_input("Enter the TikTok video URL")

    if st.button("Process URL"):
        if url:
            # Sequence of operations
            download_tiktok(url)
            obtain_audio("./downloaded_video.mp4")
            text = execute_transcription()
            if text:
                locations = execute_gpt(text)
                update_sheet(locations)
                st.success("Processing completed.")
            else:
                st.error("Errored while executing audio transcription.")
        else:
            st.error("Please enter a URL.")


if __name__ == "__main__":
    main()
