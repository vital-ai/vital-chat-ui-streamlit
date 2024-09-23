import json
import logging
import re
import streamlit as st
import time
import asyncio
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
            # response = st.write_stream(response_generator(prompt))

            message_placeholder = st.empty()
            full_response = ""
            for word in response_generator(prompt):
                full_response += word
                message_placeholder.write(full_response, unsafe_allow_html=True)

            # logger.info(f"Full Response Text: {full_response}")
            message_placeholder.write(full_response, unsafe_allow_html=True)

            book_card_html = """
            <div style="border: 1px solid #ddd; border-radius: 10px; padding: 10px; max-width: 350px; background-color: #f9f9f9; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">
                <img src="https://m.media-amazon.com/images/I/A1U18nHbNNL._SL1500_.jpg" alt="Book Cover" 
                     style="width: 100%; height: auto; object-fit: contain; border-radius: 5px;">
                <h3 style="font-size: 1.2em; margin: 10px 0;">Sea of Tranquility</h3>
                <p>Author: Emily St. John</p>
                <p>Price: $19.99</p>
                <button style="background-color: #007bff; color: white; border: none; padding: 10px 20px; text-align: center; 
                                text-decoration: none; display: inline-block; font-size: 14px; border-radius: 5px; cursor: pointer;">
                    Buy Now
                </button>
            </div>
            """
            # testing simple card
            # st.components.v1.html(book_card_html, height=800)

        # st.session_state.messages.append({"role": "assistant", "content": response})
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

