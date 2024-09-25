import json
import logging
import re
import threading
import streamlit as st
import time
import asyncio
import uvicorn
from ai_haley_kg_domain.model.KGChatBotMessage import KGChatBotMessage
from ai_haley_kg_domain.model.KGChatUserMessage import KGChatUserMessage
from ai_haley_kg_domain.model.KGToolRequest import KGToolRequest
from ai_haley_kg_domain.model.KGToolResult import KGToolResult
from com_vitalai_aimp_domain.model.AIMPIntent import AIMPIntent
from com_vitalai_aimp_domain.model.AgentMessageContent import AgentMessageContent
from com_vitalai_aimp_domain.model.UserMessageContent import UserMessageContent
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
import threading


logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)


class LocalMessageHandler(AIMPMessageHandlerInf):

    def __init__(self):
        self.response_list = []

    async def receive_message(self, message):
        print(f"Local Handler Received message: {message}")
        self.response_list.append(message)
        return

    def get_response(self):
        return self.response_list


class ChatSessionState:
    session_id: str
    session_history: list = []


account_uri: str
login_id: str
username: str
use_streamlit_session_id: bool
session_id: str


def main():

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

    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()

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

        st.session_state.messages.append({"role": "assistant", "content": full_response})


def get_response(response_list):

    vs = VitalSigns()

    session_state = st.session_state.chat_session

    logger = logging.getLogger(__name__)

    response = ""

    for response_msg in response_list:

        logger.info(f"get_response: response_msg: {response_msg}")

        message_list = []

        for m in response_msg:
            m_string = json.dumps(m)
            go = vs.from_json(m_string)
            message_list.append(go)

        for m in message_list:

            if isinstance(m, AgentMessageContent):
                agent_text = str(m.text)
                response = response + "\n" + agent_text

            if isinstance(m, HaleyContainer):
                container_in = m
                object_list = VitalSignsUtils.unpack_container(container_in)
                for o in object_list:
                    logger.info(f"Object: {o.to_json(pretty_print=False)}")
                    session_state.session_history.append(o)

    return response


def generate_history_list(message_list):

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

    return history_list


async def generate_responses(prompt_message):

    logger = logging.getLogger(__name__)

    vs = VitalSigns()

    handler = LocalMessageHandler()

    # external to docker
    # client = VitalAgentContainerClient("http://localhost:7007", handler)

    # within docker
    client = VitalAgentContainerClient("http://host.docker.internal:7007", handler)

    health = await client.check_health()

    logger.info("Health:", health)

    await client.open_websocket()

    # hasSessionID
    # hasAuthSessionID
    # hasAccountURI
    # hasUserID (email)
    # hasUsername (First and Last name)

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

    history_list = generate_history_list(st.session_state.messages[:-1])

    message = [aimp_msg, user_content]

    if len(history_list) > 0:
        container_out = HaleyContainer()
        container_out.URI = URIGenerator.generate_uri()
        container_out = VitalSignsUtils.pack_container(container_out, history_list)
        message.append(container_out)

    # string
    message_json = vs.to_json(message)
    # list of dict
    message_list = json.loads(message_json)

    await client.send_message(message_list)
    await client.wait_for_close_or_timeout(60)
    await client.close_websocket()

    logger.info(f"Client Closed")

    response_list = handler.get_response()

    response = get_response(response_list)

    logger.info(f"Response Text: {response}")

    # for word in response.split():
    #    yield word + " "
    #    time.sleep(0.05)

    tokens = re.split(r'(\s+)', response)
    for token in tokens:
        yield token
        if not token.isspace():
            time.sleep(0.05)


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

