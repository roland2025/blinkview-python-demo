# BlinkView python logging integration example

A backend service and a client application, managed seamlessly using `uv`.

## Screenshots of what to expect

### Demo Client UI

![Demo Client UI](https://raw.githubusercontent.com/roland2025/blinkview-extra/refs/heads/main/screenshots/python_client_server_ui.png)

### BlinkView integration

![BlinkView LogViewer and filter](https://raw.githubusercontent.com/roland2025/blinkview-extra/refs/heads/main/screenshots/python_client_server_logviewer.png)

![BlinkView Unified Dashboard](https://raw.githubusercontent.com/roland2025/blinkview-extra/refs/heads/main/screenshots/python_client_server_main.jpg)

![BlinkView Plotting](https://raw.githubusercontent.com/roland2025/blinkview-extra/refs/heads/main/screenshots/python_client_server_plot.png)

---

## Getting Started

### 1. Install BlinkView

Install the core logging viewer using the native package platform or instructions provided in
the [🖥️ BlinkView GitHub Repository](https://github.com/roland2025/blinkview).

### 2. Install UV (Dependency Manager)

> 💡 **Note:** Skip this step if you already installed BlinkView or if you already have `uv` installed on your machine.

This project uses **uv** for blazing-fast, isolated dependency resolution. If it isn't installed yet, run the
appropriate command for your operating system:

* **macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh

```

* **Windows (PowerShell):**

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

```

### 3. Setup This Demo App

Once your environment tools are ready, configure the demo app workspace:

1. **Clone the repository** and navigate to the project directory:

```bash
git clone https://github.com/roland2025/blinkview-python-demo.git
cd blinkview-python-demo

```

2. **Sync the environment:**
   Download the correct Python version automatically, spin up a localized virtual environment (`.venv`), and hook up the
   local packages along with their script execution entry points:

```bash
uv sync

```

---

## Running the Application

`uv run` ensures that the scripts execute within the context of the project's virtual environment, automatically
handling module resolution and dependency paths.

### Option 1: Run via the Client UI (Recommended)

The easiest way to run the application is to start the client application directly. The UI includes a built-in manager
to launch the headless backend service seamlessly without opening separate terminal windows.

1. **Launch the Client:**

```bash
uv run client

```

2. **Start the Backend:** Click the **"Start backend"** button inside the *Network Status* box at the top of
   the window to spin up the backend service instantly.

---

### Option 2: Run via Separate Terminal Windows (Manual)

If you are debugging or prefer to see distinct terminal outputs from both services, you can run the components manually
in separate processes:

1. **Start the Backend First:**
   The backend service processes data and handles incoming connections. Run it in your first terminal window:

```bash
uv run backend

```

2. **Start the Client:**
   Open a **new terminal window/pane** and launch the client interface to connect to your running backend:

```bash
uv run client

```

---

### 3. Stream Live Logs

To view application logs on the fly using `blinkview`, open a new terminal pane, make sure you are in the project
folder, and run:

```bash
blink

```