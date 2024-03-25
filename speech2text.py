import requests
from moviepy.editor import *
import whisper
from langchain.llms import OpenAI
from googleapiclient.discovery import build
from google.oauth2 import service_account
import streamlit as st
import json
import tempfile
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate


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

    video_clip = VideoFileClip(file_path)

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
    # llm = OpenAI(api_key=st.secrets["openai"], model_name="gpt-3.5-turbo-instruct")
    llm = ChatAnthropic(
        temperature=0,
        anthropic_api_key=st.secrets["anthropic"],
        model_name="claude-3-haiku-20240307",
    )

    transcribed_text = f"{text}"

    # prompt = [
    #     f"""You are a travel expert specializing in Japan and Korea. Identify all restaurants/attractions/tips mentioned in the following tiktok audio transcript with city,state,country they are located in: {transcribed_text}.
    #     Include area of city as part of location (ie. Shibuya, Dotunburi, Itaewon, etc). If place name or city is unclear, infer using context (ie. Korean won -> Korea).
    #     If an item is dining/attraction, give response in this strict format with 'Place Name', 'Location' and 'Notes': "'Name: _, Location: _, Notes: _', where 'Notes'" is any recommendations at that dining place or attraction mentioned in the transcript. If it is a tip, give summarized tip (in 20-40 words) in this strict format: 'Tip: _, Location: _'"""
    # ]

    # response = llm.generate(prompt)
    system = """You are a travel expert specializing in Japan and Korea. Identify all restaurants/attractions/tips mentioned in the following tiktok audio transcript with city,state,country they are located in. 
    #     Include area of city as part of location (ie. Shibuya, Dotunburi, Itaewon, etc). If place name or city is unclear, infer using context (ie. Korean won -> Korea). 
    #     If an item is dining/attraction, give response in this extremely strict format with Name, Location, and Notes: "'Name: _, Location: _, Notes: _', where 'Notes'" is any recommendations at that dining place or attraction mentioned in the transcript. If it is a tip, give summarized tip (in 20-40 words) in this extremely strict format w/ Tip and Location: 'Tip: _, Location: _'"""
    human = "{transcribed_text}"
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])

    chain = prompt | llm
    response = chain.invoke(
        {
            "transcribed_text": transcribed_text,
        }
    )
    # output = response.generations[0][0].text.strip()
    output = response.content.strip()
    st.info(f"GPT Output: {output}")

    locations = output.split("\n")
    dining_attractions = []
    tips = []
    for loc in locations:
        if "Place Name: " in loc and "Location: " in loc and "Notes: " in loc:
            dining_attractions.append(loc)
        elif "Tip: " in loc:
            tips.append(loc)
    if dining_attractions:
        st.info(f"Dining/Attractions: {dining_attractions}")
    if tips:
        st.info(f"Tips: {tips}")
    return dining_attractions, tips


SPREADSHEET_ID = st.secrets["sheet_id"]
SHEET_NAME = "Dining/Attractions"
SHEET_NAME2 = "Tips"


def load_credentials():
    data = json.loads(st.secrets["sheet_secret"])
    filename = "googlesheets_pk.json"

    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

    credentials = service_account.Credentials.from_service_account_file(filename)
    return credentials


def update_sheet(dining_attractions, credentials):
    rows_to_insert = []
    for location in dining_attractions:
        split_loc = location.split(", Location: ")
        name = split_loc[0].split("Place Name: ")[1]
        split_notes = split_loc[1].split(", Notes:")
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


def update_sheet2(tips, credentials):
    rows_to_insert = []
    for location in tips:
        tip_split = location.split("Tip: ")
        loc_split = tip_split[1].split(", Location: ")
        tip = loc_split[0]
        loc = loc_split[1]
        rows_to_insert.append([tip, loc])
        st.info(f"Adding tip: {tip} - {loc}")

    service = build("sheets", "v4", credentials=credentials)

    request_body = {"values": rows_to_insert}
    response = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME2}!A:D",
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
            download_tiktok(url)
            text = obtain_audio("./downloaded_video.mp4")
            if text:
                dining_attractions, tips = execute_gpt(text)
                update_sheet(dining_attractions, credentials)
                update_sheet2(tips, credentials)
                st.success("Processing completed.")
            else:
                st.error("Errored while executing audio transcription.")
        else:
            st.error("Please enter a URL.")


if __name__ == "__main__":
    main()
