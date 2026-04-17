# Appendix: Claude Computer Use Agent Background

### **Time Allocation Guidance**

<aside>
💡

*We highly recommend using AI coding tools (e.g., Cursor, Windsurf, Claude Code, Gemini CLI, CodeX) to **assist** you. However, complete vibe coding without on top of your codebase will result in automatic rejection.*

</aside>

*This is primarily a backend role assessment. A simple frontend demo is sufficient - use tools like lovable.dev or basic HTML/JavaScript. No frontend experience needed.*

- **Read the codebase and play with it (1 hour)**
- **Backend API (1.5 hours)**:
    - **Core FastAPI features**: Start a new task session, Interact with agent, Task history management, VM instance management.
    - **Computer Use Integration**: Integrating the Anthropic demo agent
    - **Database Layer**: Data persistence, basic CRUD
    - **Simultaneous Concurrency Handling**: Support concurrent session requests
- **Docker compose (0.5 hour)**
- **Frontend Demo (0.5 hour)**: Simple interface to test APIs; include VNC connection
- **Documentation (0.5 hour)**: README with dev setup instruction, API docs, sequence diagram and demo video with sound

## **0. Anthropic API Key Access:**

- Global Candidates: https://platform.claude.com/settings/keys
- Chinese Candidates: https://www.packyapi.com/console/token
    - Use available token groups anthropic aws-q / aws-q-sale (x0.15) https://www.packyapi.com/pricing

## 1. Background

**Computer Use** is a breakthrough capability that lets AI agents control computers like humans do - taking screenshots, clicking buttons, typing text, and navigating software interfaces.

**Learn more**:

- [Anthropic Demo Video](https://www.youtube.com/watch?v=ODaHJzOyVCQ)
- [Technical Deep Dive](https://www.youtube.com/watch?v=VDmU0jjklBo)

You are provided with the following starting stack:

- **Download**: https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo
- **Current Setup**: Experimental Claude Computer Use stack with Streamlit interface, runs at `http://localhost:8080`
- **Functionality**: Basic chat interface + VNC screen view + Computer Use API integration

### Current Architecture

Due to limitations with Streamlit, the goal is to rebuild the application using a genuine backend API approach.

![image.png](attachment:0d3cfef5-25b1-4139-9bb1-a125dc1cb6a2:image.png)

## 2. Session Management Features

**Session Management**

Design a backend system that treats each task as a **chat session**. Every user query and each response (including function calls and tool execution results) should be managed through your API, similar to ChatGPT. The UI example above illustrates this concept:

- **Left Bar**: Shows the **Task History**. Below it, there is a button to **Start a New Agent Task**.
- **Middle Panel**: Displays a **VNC connection** to the running virtual machine, allowing users to see what the agent is doing.
- **Right Panel (Top)**: Acts as the **Chat Session** area, listing all messages, including user queries, model responses, function calls, and results `in realtime`.
- **Right Panel (Bottom)**: Reserved for **File Management**
    
    ![image.png](attachment:dfe2d1ad-76a3-46cf-88c1-14e56015978c:image.png)
    

**Core Components to Design:**

- **API Design**: RESTful endpoints and WebSocket, Server-Sent Events (SSE), or your chosen  connections for real-time communication
- **VNC Connection**: Integration with the existing VNC server to provide screen access
- **Database**: Persistent storage for session data, chat history, and task results
- **Computer Use Integration**: Seamless integration with the existing Anthropic Computer Use agent loop
- **Concurrency Handling**: Your system must handle concurrent session requests without race conditions at the same time.

**Key API Functionality:**

- Start new agent task sessions
- Send user queries to active sessions
- Stream real-time progress updates from the computer use agent
- Retrieve past session history and interactions
- Handle concurrent session requests gracefully

This structure provides a clear, chat-like interface where users can easily follow each step of their session, review past interactions, and start or end tasks as needed - all through well-designed backend APIs.

## 3. Technical Requirements

The revised target architecture requires:

1. **Backend:** A `Python FastAPI` system serving as the core API for session management
    1. **reusing computer use agent stack of this github repo:** https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo
    2. ***Removing the experimental streamlit layer***, while adding missing backend API, database, etc layer.
    3. Ensuring the system handles concurrent session requests without race conditions.
    4. Building docker image and compose for both local development and production deployment.
    
    ![image.png](attachment:71346550-8ead-427c-b9aa-b2742e5c4290:image.png)
    
2. **Frontend:** Simple interface for testing backends APIs (***Swagger, OpenAPI, and Streamlit is not allowed***) - use tools like [lovable.dev](https://lovable.dev/) or basic HTML/JavaScript. No frontend experience needed. The UI example below shows the general concept of session management and real-time progress tracking.

This new architecture focuses on building a robust, maintainable backend system that can integrate with any frontend.

## **4. Deliverables**

- Please commit all your work in a private GitHub repository with a detailed README, including:
    1. Your full name on the first line of the README (e.g. `Author: ...`)
    2. A fully functional implementation of the proposed architecture.
    3. A 5-minute demo video with sound
        1. **Repository and Codebase Overview**
        2. **Service Launch and Endpoint Functionality**
        3. **Usage Case Demonstrations**
            1. **Usage Case 1:**
                1. Start a new chat session
                2. Use the prompt “Search the weather in Dubai”.
                3. Verify that the system correctly opens Firefox, conducts a Google search for the weather in Dubai, and provides a summarized result in `realtime`.
            2. **Usage Case 2 (Simultaneous Concurrent Sessions — STRICTLY NON-BLOCKING):**
                1. While a task is actively running (e.g., "Search the weather in Tokyo"), submit another task request simultaneously from a different session (e.g., "Search the weather in New York").
                2. **Requirement:** You must demonstrate that both requests are processing **at the exact same time** (in parallel). The second task **MUST NOT wait** for the first task to finish before starting. Sequential processing (queuing) will be considered a failure!!!
                3. Any solution that is hard-coded to support `a fixed number of concurrent sessions` (e.g., only 2) as well as `multiple display` for demo only will also be considered a **failure!!! The architecture must dynamically spawn worker for even new incoming request.**
                4. Show how your system manages these concurrent threads/processes without race conditions or system errors.
                5. **Visual Verification:** Arrange two **windows** side-by-side on your desktop screen (e.g., two separate browser tabs representing User A and User B). Trigger the requests in each. Verify that the system correctly opens two **separate Firefox automation windows simultaneously**, conducting the Google search for the weather (one for Tokyo, one for New York) at the same time, and provides a summarized result in `realtime`.
        4. **Streamlit-like UI Behavior Simulation**
            1. Illustrate that when a task is submitted, the AI agent streams real-time progress for each intermediate step.
            2. Once the task is complete, demonstrate that the UI prompts the user to enter a new task.
    4. Use this README as the ONLY place to deliver your work. Please don’t send any of the above details via email (not all reviewers have access to emails).
- Invite`lingjiekong`, `ghamry03` , `goldmermaid`, and `EnergentAI` as collaborators for review.
- Once you complete your homework, please kindly reply our email with your private github repo link, as a homework completion notice.

## **5. Evaluation**

All documentation must be written in clear, concise `English` to ensure that every team member can easily understand the project. Your work will be evaluated based on the following clear metrics:

- **Backend Design (40%)**
    - API design and architecture
    - Session management implementation
    - **Handling of concurrent session requests**
- **Real-time Streaming (25%)**
    - WebSocket/SSE implementation
    - Progress updates and status feedback
- **Code Quality (20%)**
    - Clean, maintainable code
    - Proper error handling
    - Robust concurrent request handling
- **Documentation (15%)**
    - README completeness
    - API documentation
    - Sequence diagrams