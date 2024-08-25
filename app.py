import json
import streamlit as st
import time
import asyncio
from com_vitalai_aimp_domain.model.AIMPIntent import AIMPIntent
from com_vitalai_aimp_domain.model.AgentMessageContent import AgentMessageContent
from com_vitalai_aimp_domain.model.UserMessageContent import UserMessageContent
from vital_agent_container_client.aimp_message_handler_inf import AIMPMessageHandlerInf
from vital_agent_container_client.vital_agent_container_client import VitalAgentContainerClient
from vital_ai_vitalsigns.utils.uri_generator import URIGenerator
from vital_ai_vitalsigns.vitalsigns import VitalSigns


class LocalMessageHandler(AIMPMessageHandlerInf):

    def __init__(self):
        self.response_list = []

    async def receive_message(self, message):
        print(f"Local Handler Received message: {message}")
        self.response_list.append(message)


def main():

    vs = VitalSigns()

    hide_streamlit_controls()

    st.title("Testing Agent")

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
            response = st.write_stream(response_generator(prompt))

        st.session_state.messages.append({"role": "assistant", "content": response})


def response_generator(prompt):

    async def generate_responses(prompt_message):

        vs = VitalSigns()

        handler = LocalMessageHandler()

        # client = VitalAgentContainerClient("http://localhost:7007", handler)

        client = VitalAgentContainerClient("http://host.docker.internal:7007", handler)

        health = await client.check_health()

        print("Health:", health)

        await client.open_websocket()

        aimp_msg = AIMPIntent()
        aimp_msg.URI = URIGenerator.generate_uri()
        aimp_msg.aIMPIntentType = "http://vital.ai/ontology/vital-aimp#AIMPIntentType_CHAT"

        user_content = UserMessageContent()
        user_content.URI = URIGenerator.generate_uri()
        user_content.text = prompt_message

        message = [aimp_msg, user_content]
        # string
        message_json = vs.to_json(message)
        # list of dict
        message_list = json.loads(message_json)

        await client.send_message(message_list)
        await client.wait_for_close_or_timeout(60)

        response_list = handler.response_list

        response = ""

        for response_msg in response_list:
            # print(response_msg)
            message_list = []
            for m in response_msg:
                m_string = json.dumps(m)
                go = vs.from_json(m_string)
                message_list.append(go)
            for m in message_list:
                if isinstance(m, AgentMessageContent):
                    agent_text = str(m.text)
                    response = response + "\n" + agent_text

        for word in response.split():
            yield word + " "
            time.sleep(0.05)

        await client.close_websocket()

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

