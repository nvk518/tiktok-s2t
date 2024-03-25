import requests
import re
from moviepy.editor import *
import whisper
from langchain.llms import OpenAI
from googleapiclient.discovery import build
from google.oauth2 import service_account
import streamlit as st
import io
import json
import tempfile


@st.cache_data(max_entries=10, show_spinner=True, persist="disk")
def download_tiktok(url):
    querystring = {"url": url}

    headers = {
        "X-RapidAPI-Key": st.secrets["X_RapidAPI_Key"],
        "X-RapidAPI-Host": st.secrets["X_RapidAPI_Host"],
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


@st.cache_data(max_entries=10, show_spinner=True, persist="disk")
def obtain_audio(file_path):

    # Replace 'your_video.mp4' with the path to your video file
    video_clip = VideoFileClip(file_path)

    # Replace 'output_audio.mp3' with the desired output MP3 file name
    st.info("TikTok to audio conversion successful.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmpfile:
        audio_file_path = tmpfile.name
        video_clip.audio.write_audiofile(audio_file_path)
    model = whisper.load_model("base")
    result = model.transcribe(audio_file_path)
    # os.remove(audio_file_path)
    print(result["text"])
    st.info(f"Transcription Successful: {result['text']}")
    return result["text"]


def execute_gpt(text):
    llm = OpenAI(api_key=st.secrets["openai"])

    transcribed_text = f"{text}"

    prompt = [
        # f"Identify all restaurants/attractions mentioned in the following tiktok audio transcript with city, state, country they are located in: {transcribed_text}. Include area as part of location (ie. Shibuya, Dotunburi, etc). If place name is unclear (ie. the text transcript says Booted In, but could instead be Boudin Bakery in San Francisco), try fixing it. provide what the transcript says was a recommended item. Provide your response in this strict format: 'Name: _, Location: _, Notes: _'"
        "repeat this: Name: Boudin, Location: San Francisco, CA, Notes: Soup"
    ]

    response = llm.generate(prompt)

    print(response)
    output = response.generations[0][0].text.strip()
    locations = output.split("\n")
    return locations


# Sheets API setup
# SHEETS_SERVICE_ACCOUNT_FILE = "./googlesheets_pk.json"
SPREADSHEET_ID = st.secrets["sheet_id"]
SHEET_NAME = "Sheet2"


def load_credentials():
    data = json.loads(st.secrets["sheet_secret"])
    filename = "googlesheets_pk.json"

    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

    credentials = service_account.Credentials.from_service_account_file(filename)
    return credentials


def update_sheet(locations, credentials):
    rows_to_insert = []
    for location in locations:
        split_loc = location.split(", Location: ")
        name = split_loc[0].split("Name: ")[1]
        split_notes = split_loc[1].split(", Notes/Recommendations:")
        location = split_notes[0]
        notes = split_notes[1]
        rows_to_insert.append([name, location, notes])
        st.info(f"Adding location: {name} - {location}")

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


def main():
    st.title("TikTok Processor")

    url = st.text_input("Enter the TikTok video URL")
    credentials = load_credentials()
    if st.button("Process URL"):
        if url:
            # Sequence of operations
            download_tiktok(url)
            text = obtain_audio("./downloaded_video.mp4")
            # text = execute_transcription()
            if text:
                locations = execute_gpt(text)
                update_sheet(locations, credentials)
                st.success("Processing completed.")
            else:
                st.error("Errored while executing audio transcription.")
        else:
            st.error("Please enter a URL.")


if __name__ == "__main__":
    main()
