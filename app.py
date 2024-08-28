import json
import logging
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


def main():

    vs = VitalSigns()

    hide_streamlit_controls()

    st.title("Testing Agent")

    logger = logging.getLogger(__name__)

    logger.info("Chat UI Starting Up...")

    # session_id = get_session_id()

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

        # logger.info(st.session_state.messages)

        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            response = st.write_stream(response_generator(prompt))

        st.session_state.messages.append({"role": "assistant", "content": response})


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
                # handle here?
                # logger.info(f"HaleyContainer: {m.to_json(pretty_print=False)}")
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

    # client = VitalAgentContainerClient("http://localhost:7007", handler)

    client = VitalAgentContainerClient("http://host.docker.internal:7007", handler)

    health = await client.check_health()

    logger.info("Health:", health)

    await client.open_websocket()

    aimp_msg = AIMPIntent()
    aimp_msg.URI = URIGenerator.generate_uri()
    aimp_msg.aIMPIntentType = "http://vital.ai/ontology/vital-aimp#AIMPIntentType_CHAT"

    user_content = UserMessageContent()
    user_content.URI = URIGenerator.generate_uri()
    user_content.text = prompt_message

    # logger.info(st.session_state.messages)

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

    for word in response.split():
        yield word + " "
        # await asyncio.sleep(0.05)
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

