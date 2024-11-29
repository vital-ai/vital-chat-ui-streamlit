import json
import logging
import re
import streamlit as st
import time
import asyncio
import uvicorn
from ai_chat_domain.model.HaleyChatBotMessage import HaleyChatBotMessage
from ai_chat_domain.model.HaleyChatIntent import HaleyChatIntent
from ai_chat_domain.model.HaleyChatInteraction import HaleyChatInteraction
from ai_chat_domain.model.HaleyChatUserMessage import HaleyChatUserMessage
from ai_haley_kg_domain.model.KGChatBotMessage import KGChatBotMessage
from ai_haley_kg_domain.model.KGChatUserMessage import KGChatUserMessage
from ai_haley_kg_domain.model.KGToolRequest import KGToolRequest
from ai_haley_kg_domain.model.KGToolResult import KGToolResult
from com_vitalai_aimp_domain.model.AIMPIntent import AIMPIntent
from com_vitalai_aimp_domain.model.AgentMessageContent import AgentMessageContent
from com_vitalai_aimp_domain.model.HaleyWeatherMessage import HaleyWeatherMessage
from com_vitalai_aimp_domain.model.UserMessageContent import UserMessageContent
from com_vitalai_aimp_domain.model.WeatherForecast import WeatherForecast
from com_vitalai_haleyai_question_domain.model.HaleyContainer import HaleyContainer
from vital_agent_container_client.aimp_message_handler_inf import AIMPMessageHandlerInf
from vital_agent_container_client.vital_agent_container_client import VitalAgentContainerClient
from vital_agent_kg_utils.vitalsignsutils.vitalsignsutils import VitalSignsUtils
from vital_ai_vitalsigns.utils.uri_generator import URIGenerator
from vital_ai_vitalsigns.vitalsigns import VitalSigns
from vital_chat_ui_app.utils.config_utils import ConfigUtils
from jinja2 import Environment, FileSystemLoader
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from datetime import datetime


logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)


class LocalMessageHandler(AIMPMessageHandlerInf):

    def __init__(self):
        self.response_list = []

    async def receive_message(self, message):
        logger = logging.getLogger(__name__)
        logger.info(f"Local Handler Received message: {message}")
        self.response_list.append(message)
        return

    def get_response(self):
        return self.response_list


class ChatSessionState:
    session_id: str
    session_history: list = []


message_domain: str

chat_interaction_type: str

agent_hostname: str
agent_port: int
agent_path: str

account_uri: str
login_id: str
username: str
use_streamlit_session_id: bool
session_id: str


def transform(input_data):
    icon_mapping = {
        0: "wi-day-sunny",  # Clear sky
        1: "wi-day-sunny-overcast",  # Mainly clear
        2: "wi-day-cloudy",  # Partly cloudy
        3: "wi-day-cloudy",  # Overcast
        45: "wi-fog",  # Fog
        48: "wi-fog",  # Depositing rime fog
        51: "wi-day-showers",  # Drizzle: Light
        53: "wi-day-showers",  # Drizzle: Moderate
        55: "wi-day-storm-showers",  # Drizzle: Dense
        61: "wi-day-rain",  # Rain: Slight
        63: "wi-day-rain",  # Rain: Moderate
        65: "wi-day-rain",  # Rain: Heavy
        66: "wi-day-sleet",  # Freezing rain: Light
        67: "wi-day-sleet",  # Freezing rain: Heavy
        71: "wi-day-snow",  # Snow fall: Slight
        73: "wi-day-snow",  # Snow fall: Moderate
        75: "wi-day-snow",  # Snow fall: Heavy
        77: "wi-snowflake-cold",  # Snow grains
        80: "wi-day-showers",  # Rain showers: Slight
        81: "wi-day-showers",  # Rain showers: Moderate
        82: "wi-day-showers",  # Rain showers: Violent
        85: "wi-day-snow",  # Snow showers: Slight
        86: "wi-day-snow",  # Snow showers: Heavy
        95: "wi-thunderstorm",  # Thunderstorm: Slight or moderate
        96: "wi-thunderstorm",  # Thunderstorm with slight hail
        99: "wi-thunderstorm"  # Thunderstorm with heavy hail
    }

    description_mapping = {
        0: "Sunny",
        1: "Sunny and Overcast",
        2: "Partly cloudy",
        3: "Cloudy",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light Rain",
        53: "Moderate Rain",
        55: "Storm Showers",
        61: "Slight Rain",
        63: "Moderate Rain",
        65: "Heavy Rain",
        66: "Sleet and Freezing Rain",
        67: "Heavy Sleet and Freezing Rain",
        71: "Light Snow",
        73: "Moderate Snow",
        75: "Heavy Snow",
        77: "Snowflakes",
        80: "Slight Rain Showers",
        81: "Moderate Rain Showers",
        82: "Heavy Rain Showers",
        85: "Slight Snow",
        86: "Heavy Snow",
        95: "Thunderstorm",
        96: "Thunderstorm and Hail",
        99: "Thunderstorm and Heavy Hail"
    }

    # Transform the data
    transformed_data = {
        "searchString": input_data["place_label"],
        "mainIcon": icon_mapping.get(input_data["weather_code"], "wi-day-sunny"),
        "summary": description_mapping.get(input_data["weather_code"], input_data["weather_code_description"]),
        "temperature": round(input_data["temperature"]),
        "precipitation": input_data["precipitation_probability"],
        "humidity": input_data["humidity"],
        "wind": round(input_data["wind_speed"]),
        "days": [
            {
                "dow": datetime.strptime(day["date"], "%Y-%m-%d").strftime("%a"),
                "icon": icon_mapping.get(day["weather_code"], "wi-day-sunny"),
                "maxTemp": round(day["temperature_max"]),
                "minTemp": round(day["temperature_min"])
            }
            for day in input_data["daily_predictions"][:7]
        ],
        "staticCard": False,
        "agentWeatherLink": f'https://www.chat.ai'
    }

    return transformed_data



def main():

    global message_domain

    global chat_interaction_type

    global agent_hostname
    global agent_port
    global agent_path

    global account_uri
    global login_id
    global username
    global use_streamlit_session_id

    global session_id

    vs = VitalSigns()

    hide_streamlit_controls()

    st.title("Testing Agent")

    logger = logging.getLogger(__name__)

    logger.info("Chat UI Starting Up...")

    config = ConfigUtils.load_config()

    logger.info("Chat UI Config Loaded.")

    app = FastAPI()

    # using websocket as its more forgiving for localhost security
    # and because we want two-way communication
    # initial testing is with "cards" which have a button which can trigger
    # a message being sent to the agent.  due to how streamlit works, the python side will send the message.
    # the full implementation has the javascript side sending the message.

    # to test the client side more we may want to include vitalsigns js and the domains
    # on the browser side, but the immediate need is to test the basic capability of
    # displaying "cards" in the UI that contain data from the agent to validate agent functionality.

    # note: important to open the port for the websocket for docker

    @app.get("/")
    async def get():
        return HTMLResponse("WebSocket server is running!")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        while True:
            data = await websocket.receive_text()
            logger.info(f"WebSocket received message: {data}")
            await websocket.send_text(f"Message received: {data}")

    def run_api():
        uvicorn.run(app, host="0.0.0.0", port=8999)

    # api_thread = threading.Thread(target=run_api, daemon=True)
    # api_thread.start()

    env = Environment(loader=FileSystemLoader('templates'))

    product_card_template = env.get_template('product_card.jinja2')

    rendered_product_card = product_card_template.render()

    sample_weather_data = {
        "searchString": "New York City",
        "mainIcon": "wi-day-sunny",
        "summary": "Clear skies with sunshine",
        "temperature": 75,
        "precipitation": 10,
        "humidity": 60,
        "wind": 12,
        "days": [
            {"dow": "Mon", "icon": "wi-day-cloudy", "maxTemp": 79, "minTemp": 70},
            {"dow": "Tue", "icon": "wi-day-rain", "maxTemp": 75, "minTemp": 68},
            {"dow": "Wed", "icon": "wi-day-sunny", "maxTemp": 85, "minTemp": 72},
            {"dow": "Thu", "icon": "wi-day-storm-showers", "maxTemp": 77, "minTemp": 69},
            {"dow": "Fri", "icon": "wi-day-fog", "maxTemp": 78, "minTemp": 70}
        ],
        "staticCard": False,
        "forecastIoLink": "https://weather.com"
    }

    weather_card_template = env.get_template('weather_card.jinja2')

    rendered_weather_card = weather_card_template.render(sample_weather_data)

    chat_config = config['vital_chat_ui']

    message_domain = chat_config['message_domain']

    chat_interaction_type = chat_config['chat_interaction_type']

    agent_hostname = chat_config['agent_hostname']
    agent_port = chat_config['agent_port']
    agent_path = chat_config['agent_path']

    account_uri = chat_config['account_uri']
    login_id = chat_config['login_id']
    username = chat_config['username']
    use_streamlit_session_id = chat_config['use_streamlit_session_id']

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(id(st.session_state))

    session_id = st.session_state.session_id

    logger.info(f"Session ID: {session_id}")

    if "chat_session" not in st.session_state:
        st.session_state.chat_session = ChatSessionState()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and "html" in message:
                st.components.v1.html(message["content"], height=300)
            else:
                st.markdown(message["content"])

    if prompt := st.chat_input("Message to Agent"):

        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):

            message_placeholder = st.empty()
            full_response = ""
            for word in response_generator(prompt):
                full_response += word
                message_placeholder.write(full_response, unsafe_allow_html=True)

            # logger.info(f"Full Response Text: {full_response}")
            message_placeholder.write(full_response, unsafe_allow_html=True)

            # testing simple product and weather card
            # st.components.v1.html(rendered_product_card, height=800)
            # st.components.v1.html(rendered_weather_card, height=300)

        # st.session_state.messages.append({"role": "assistant", "content": full_response})


def get_response(response_list):

    vs = VitalSigns()

    session_state = st.session_state.chat_session

    logger = logging.getLogger(__name__)

    response = ""

    for response_msg in response_list:

        # logger.info(f"get_response: response_msg: {response_msg}")

        message_list = []

        unpacked_message_list = []

        for m in response_msg:
            m_string = json.dumps(m)
            go = vs.from_json(m_string)
            message_list.append(go)

        for m in message_list:

            # TODO return card(s) in response?

            if isinstance(m, HaleyContainer):
                container_in = m
                object_list = VitalSignsUtils.unpack_container(container_in)
                for o in object_list:
                    logger.info(f"Object: {o.to_json(pretty_print=False)}")
                    session_state.session_history.append(o)
                    unpacked_message_list.append(o)
            else:
                unpacked_message_list.append(m)

        for m in unpacked_message_list:

            if isinstance(m, AgentMessageContent):
                agent_text = str(m.text)
                response = response + "\n" + agent_text

            if isinstance(m, HaleyChatBotMessage):
                if m.chatGeneratedMessage:
                    agent_text = str(m.chatGeneratedMessage)
                    response = response + "\n" + agent_text

    return response


def generate_history_list(message_list, message_domain: str):

    history_list = []

    session_state = st.session_state.chat_session

    for message in session_state.session_history:

        if isinstance(message, KGToolRequest):
            history_list.append(message)

        if isinstance(message, KGToolResult):
            history_list.append(message)

    for m in message_list:
        role = m["role"]
        content = m["content"]

        if message_domain == "vital-ai-aimp":

            if role == "user":
                user_message = KGChatUserMessage()
                user_message.URI = URIGenerator.generate_uri()
                user_message.kGChatMessageText = content
                history_list.append(user_message)

            if role == "assistant":
                bot_message = KGChatBotMessage()
                bot_message.URI = URIGenerator.generate_uri()
                bot_message.kGChatMessageText = content
                history_list.append(bot_message)

        if message_domain == "vital-ai-chat":
            if role == "user":
                user_message = HaleyChatUserMessage()
                user_message.URI = URIGenerator.generate_uri()
                user_message.chatTextMessage = content
                history_list.append(user_message)

            if role == "assistant":
                bot_message = HaleyChatBotMessage()
                bot_message.URI = URIGenerator.generate_uri()
                bot_message.chatGeneratedMessage = content
                history_list.append(bot_message)

    return history_list


async def generate_responses(prompt_message):

    logger = logging.getLogger(__name__)

    vs = VitalSigns()

    handler = LocalMessageHandler()

    # external to docker
    # client = VitalAgentContainerClient("http://localhost:7007", handler)

    # within docker
    client = VitalAgentContainerClient(f"http://{agent_hostname}:{agent_port}{agent_path}", handler)

    health = await client.check_health()

    logger.info("Health:", health)

    await client.open_websocket()

    # hasSessionID
    # hasAuthSessionID
    # hasAccountURI
    # hasUserID (email)
    # hasUsername (First and Last name)

    message = []

    history_list = []

    if message_domain == "vital-ai-aimp":

        aimp_msg = AIMPIntent()
        aimp_msg.URI = URIGenerator.generate_uri()
        aimp_msg.aIMPIntentType = "http://vital.ai/ontology/vital-aimp#AIMPIntentType_CHAT"

        aimp_msg.accountURI = account_uri
        aimp_msg.username = username
        aimp_msg.userID = login_id

        aimp_msg.sessionID = session_id
        aimp_msg.authSessionID = session_id

        user_content = UserMessageContent()
        user_content.URI = URIGenerator.generate_uri()
        user_content.text = prompt_message

        history_list = generate_history_list(st.session_state.messages[:-1], message_domain)

        message = [aimp_msg, user_content]

        if len(history_list) > 0:
            container_out = HaleyContainer()
            container_out.URI = URIGenerator.generate_uri()
            container_out = VitalSignsUtils.pack_container(container_out, history_list)
            message.append(container_out)

    if message_domain == "vital-ai-chat":

        interaction = HaleyChatInteraction()
        interaction.URI = URIGenerator.generate_uri()

        # this may be irrelevant in the KG case
        interaction.haleyChatInteractionModelTypeURI = "http://vital.ai/ontology/chat-ai#HaleyChatInteractionModelType_OpenAI_ChatGPT_4o"

        interaction.haleyChatInteractionTypeURI = "http://vital.ai/ontology/chat-ai#HaleyChatInteraction_CHAT"

        if chat_interaction_type == "HaleyChatInteraction_CHAT_KG":
            interaction.haleyChatInteractionTypeURI = "http://vital.ai/ontology/chat-ai#HaleyChatInteraction_CHAT_KG"

        chat_intent = HaleyChatIntent()
        chat_intent.URI = URIGenerator.generate_uri()

        chat_intent.accountURI = account_uri
        chat_intent.username = username
        chat_intent.userID = login_id

        chat_intent.sessionID = session_id
        chat_intent.authSessionID = session_id

        user_msg = HaleyChatUserMessage()
        user_msg.URI = URIGenerator.generate_uri()

        user_msg.chatTextMessage = prompt_message

        history_list = generate_history_list(st.session_state.messages[:-1], message_domain)

        container_list = [interaction]

        container_list.extend(history_list)

        container_out = HaleyContainer()
        container_out.URI = URIGenerator.generate_uri()
        container_out = VitalSignsUtils.pack_container(container_out, container_list)

        message = [chat_intent, user_msg, interaction, container_out]

    # string
    message_json = vs.to_json(message)
    # list of dict
    message_list = json.loads(message_json)

    await client.send_message(message_list)

    # long timeout for the initial vitalsigns domain loading during testing
    await client.wait_for_close_or_timeout(120)

    await client.close_websocket()

    # TODO later render messages as they are received

    logger.info(f"Client Closed")

    response_list = handler.get_response()

    # logger.info(f"Response List: {response_list}")

    # TODO response to include thinking messages, text, and any cards
    response = get_response(response_list)

    # TODO first render "thinking" message(s)
    # maybe render as a carousel allowing flipping through them?

    logger.info(f"Response Text: {response}")

    # for word in response.split():
    #    yield word + " "
    #    time.sleep(0.05)

    tokens = re.split(r'(\s+)', response)

    for token in tokens:
        yield token
        if not token.isspace():
            time.sleep(0.05)

    st.session_state.messages.append({"role": "assistant", "content": response})

    # move env to global
    # the cards render after the yields complete

    env = Environment(loader=FileSystemLoader('templates'))
    weather_card_template = env.get_template('weather_card.jinja2')

    weather_cards = []

    for response_msg in response_list:

        message_list = []

        for m in response_msg:
            m_string = json.dumps(m)
            go = vs.from_json(m_string)
            message_list.append(go)

        aimp_msg = message_list[0]

        if isinstance(aimp_msg, HaleyWeatherMessage):

            weather_card = message_list[1]

            if isinstance(weather_card, WeatherForecast):

                weather_json = str(weather_card.weatherJSONResponse)

                weather_obj = json.loads(weather_json)

                weather_data = transform(weather_obj)

                rendered_weather_card = weather_card_template.render(weather_data)

                st.components.v1.html(rendered_weather_card, height=300)

                st.session_state.messages.append({"role": "assistant", "content": rendered_weather_card, "html": True})




def response_generator(prompt):

    logger = logging.getLogger(__name__)

    async_gen = generate_responses(prompt)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        loop = asyncio.get_event_loop()
        while True:
            response_word = loop.run_until_complete(async_gen.__anext__())
            yield response_word
    except StopAsyncIteration:
        pass


def hide_streamlit_controls():

    hide_controls_style = """
    <style>
    [data-testid="stStatusWidget"] {
        visibility: hidden;
    }
    .stDeployButton {
        visibility: hidden;
    }
    </style>
    """

    st.markdown(hide_controls_style, unsafe_allow_html=True)


if __name__ == "__main__":
    main()

