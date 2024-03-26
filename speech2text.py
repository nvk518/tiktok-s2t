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
from urllib.parse import quote

SPREADSHEET_ID = st.secrets["sheet_id"]
SHEET_NAME = "Dining/Attractions"
SHEET_NAME2 = "Tips"
yelp_headers = {
    "accept": "application/json",
    "Authorization": st.secrets["yelp_secret"],
}


@st.cache_data(max_entries=3, show_spinner=True, persist="disk")
def download_video(url):
    querystring = {"url": url}
    if "tiktok" in url:
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
    elif "instagram" in url:
        headers = {
            "X-RapidAPI-Key": st.secrets["X_RapidAPI_Key"],
            "X-RapidAPI-Host": st.secrets["X_RapidAPI_Host_Instagram"],
        }

        response = requests.get(
            "https://instagram-downloader-download-instagram-videos-stories1.p.rapidapi.com/",
            headers=headers,
            params=querystring,
        )

        print(response.json())
        video_url = response.json()[0]["url"]

        response = requests.get(video_url)
    else:
        st.error("Invalid video url, please enter Reel or Tiktok url.")
    if response.status_code == 200:
        with open("downloaded_video.mp4", "wb") as file:
            file.write(response.content)
        print("Video downloaded successfully.")
    else:
        print(f"Failed to download video. Status code: {response.status_code}")


@st.cache_data(max_entries=3, show_spinner=True, persist="disk")
def obtain_audio(file_path):

    video_clip = VideoFileClip(file_path)

    st.success("TikTok to audio conversion successful.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmpfile:
        audio_file_path = tmpfile.name
        video_clip.audio.write_audiofile(audio_file_path)
    model = whisper.load_model("base")
    result = model.transcribe(audio_file_path)

    print(result["text"])
    st.info(f"Transcription Successful: {result['text']}")
    return result["text"]


def execute_gpt(text):
    # llm = OpenAI(api_key=st.secrets["openai"], model_name="gpt-3.5-turbo-instruct")
    model = "claude-3-haiku-20240307"
    llm = ChatAnthropic(
        temperature=0,
        anthropic_api_key=st.secrets["anthropic"],
        model_name=model,
    )

    transcribed_text = f"{text}"
    system = """You are a travel expert specializing in Japan and Korea. Identify all restaurants/attractions/tips mentioned in the following tiktok audio transcript with city,state,country they are located in. 
    Include area of city as part of location (ie. Shibuya, Dotunburi, Itaewon, Gion, etc). If place name or city is unclear, infer using context (ie. Korean won -> Korea). If an item is dining/attraction, give response in this extremely strict format with Name, Location, and Notes: "'Name: _, Location: _, Notes: _', where 'Notes'" is any recommendations at that dining place or attraction mentioned in the transcript. If it is a tip, give summarized tip in this extremely strict format w/ Tip and Location: 'Tip: _, Location: _'. Each must be separated by a semicolon ';'. Do not lead in with anything like 'Here are the restaurants, attractions, and tips mentioned in the transcript:'. Here is an example response:
    'Name: 200-year-old spot, Location: Kyoto, Japan, Notes: Serves traditional Yuba (tofu skin) soup';'Name: Michelin guide recommended pizza place, Location: Kyoto, Japan, Notes: Serves good pizzas';'Name: Motoi, Location: Kyoto, Japan, Notes: Michelin-recommended spot for the best gyoza (dumplings)';'Tip: Visit Kyoto during cherry blossom season, Location: Kyoto, Japan';'Tip: Try fruit sandwiches and shaped ice in Japan, Location: Japan'"""
    human = "{transcribed_text}"
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])

    chain = prompt | llm
    st.info(f"Invoking {model}...")
    response = chain.invoke(
        {
            "transcribed_text": transcribed_text,
        }
    )

    st.success("Model query successful.")
    output = response.content.strip()
    st.info(f"LLM response: {output}")
    first = output.find("Name: ")
    if first == -1:
        first = output.find("Tip: ")
        if first == -1:
            st.error("No dining/attractions/tips found!")
            return
    output = output[first:]
    locations = output.split(";")

    dining_attractions = []
    tips = []
    for loc in locations:
        if "Name: " in loc and "Location: " in loc and "Notes: " in loc:
            dining_attractions.append(loc)
        elif "Tip: " in loc:
            tips.append(loc)
    if dining_attractions:
        st.info(f"Dining/Attractions: {dining_attractions}")
    if tips:
        st.info(f"Tips: {tips}")
    return dining_attractions, tips


def load_credentials():
    data = json.loads(st.secrets["sheet_secret"])
    filename = "googlesheets_pk.json"

    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

    credentials = service_account.Credentials.from_service_account_file(filename)
    return credentials


def request_yelp_api(name, location, notes):
    rows_to_insert = []
    encoded_name = quote(name)
    encoded_location = quote(location)
    url = f"https://api.yelp.com/v3/businesses/search?location={encoded_location}&term={encoded_name}&sort_by=best_match&limit=1"
    response = requests.get(url, headers=yelp_headers)
    if response.status_code != 200:
        st.error("Error while accessing Yelp API.")
        return
    business = response.json()["businesses"]
    if business:
        first_item = business[0]
        id = first_item["id"]
        url = first_item["url"]
        full_name = first_item["name"]
        review_count = first_item["review_count"]
        rating = first_item["rating"]
        coordinates = first_item["coordinates"]
        categories = [cat["title"] for cat in first_item["categories"]]

        string_categories = ", ".join(categories)

        maps_link_coords = f"https://www.google.com/maps/?q={coordinates['latitude']},{coordinates['longitude']}"
        hyperlink_map = f'=HYPERLINK("{maps_link_coords}", "{location}")'
        hyperlink_name = f'=HYPERLINK("{url}", "{full_name}")'

        rows_to_insert = [
            hyperlink_name,
            hyperlink_map,
            string_categories,
            rating,
            review_count,
            notes,
        ]

    else:
        maps_link_coords = f"https://www.google.com/maps/?q={encoded_location}"
        hyperlink_map = f'=HYPERLINK("{maps_link_coords}", "{location}")'
        rows_to_insert = [
            name,
            hyperlink_map,
            "",
            "",
            "",
            notes,
        ]

    return rows_to_insert


def update_sheet_dining_attractions(dining_attractions, credentials):
    rows_to_insert = []
    for location in dining_attractions:
        split_loc = location.split(", Location: ")
        name = split_loc[0].split("Name: ")[1]
        split_notes = split_loc[1].split(", Notes:")
        location = split_notes[0]
        notes = split_notes[1]

        try:
            rows_to_insert.append(request_yelp_api(name, location, notes))
        except ():
            st.error("Error while parsing Yelp API response.")
            return

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


def update_sheet_tips(tips, credentials):
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

    st.title("TripTok")
    st.header("Process Flow:", divider=True)
    st.text(
        "TikTok URL --> Video download --> Audio extraction --> OpenAI Whisper audio transcription --> Claude 3 LLM text processing/summarization/categorization --> Yelp API --> Update Google Sheets",
    )

    url = st.text_input("Enter the video URL")
    credentials = load_credentials()
    if st.button("Process URL"):
        st.cache_data.clear()
        if url:
            download_video(url)
            text = obtain_audio("./downloaded_video.mp4")
            if text:
                dining_attractions, tips = execute_gpt(text)
                update_sheet_dining_attractions(dining_attractions, credentials)
                update_sheet_tips(tips, credentials)
                st.success("Processing completed.")
                sheet_url = st.secrets["sheet_url"]
                st.markdown("[View Google Sheet](%s)" % sheet_url)
                st.cache_data.clear()
            else:
                st.error("Errored while executing audio transcription.")
        else:
            st.error("Please enter a URL.")


if __name__ == "__main__":
    main()
