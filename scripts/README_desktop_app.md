# DISCOVERSE Desktop App

`scripts/desktop_examples.py` provides a desktop app named DISCOVERSE built with `tkinter`.
It does not require PySide6 or any other extra GUI dependency. The app only manages subprocesses;
DISCOVERSE/MuJoCo examples and scenes still create their own simulation windows.

## Run From Source

From the repository root:

```bash
python3 scripts/desktop_examples.py
```

Use a specific Python interpreter for examples:

```bash
python3 scripts/desktop_examples.py --python /path/to/python
```

The desktop app has two launch modes:

- `Examples`: scans Python scripts from `examples/**/*.py`.
- `Scenes`: scans runnable MJCF/MJB scenes from `models/mjcf` and starts them with `python -m mujoco.viewer --mjcf=<scene>`.

## Build Desktop App With Conda

To ship the launcher without requiring users to install Python or activate conda manually, build the onedir app from your DISCOVERSE conda environment.
Activate the environment that can already run DISCOVERSE examples:

```bash
conda activate <your-discoverse-env>
./scripts/build_desktop_conda_app.sh
```

The app will be created at:

```text
dist/DISCOVERSE/DISCOVERSE
dist/DISCOVERSE/DISCOVERSE.desktop
```

In the packaged app, Start launches an internal worker process from the same `DISCOVERSE` executable, so examples and scenes do not depend on an external Python interpreter.

PyInstaller collects the Python runtime, packages, and shared libraries from the active conda environment into `dist/DISCOVERSE/`.
The user does not need to install Python or conda to run that packaged app.
Do not launch files from `build/DISCOVERSE/`; that is PyInstaller's intermediate build directory and does not contain the `_internal` runtime resources required by the app.

If the packaged app reports `Failed to load GLFW3 shared library`, rebuild with the latest `DISCOVERSE.spec`.
The spec includes the GLFW shared libraries from the active conda environment.
If it reports `No module named 'OpenGL.platform.egl'`, rebuild with the latest `DISCOVERSE.spec`.
The spec includes PyOpenGL platform modules used by DISCOVERSE rendering imports.

## UI

The launcher supports:

- Creating a DISCOVERSE conda environment from the `Environment Setup` window.
- Choosing the conda environment name and Python version, currently `3.11` or `3.12`.
- Searching examples scanned from `examples/**/*.py`.
- Filtering examples by their first-level directory group.
- Configuring common arguments: `--auto`, `--use_gs`, `--data_idx`, `--data_set_size`.
- Adding extra command line arguments.
- Adding environment variables, one `KEY=VALUE` per line.
- Starting and stopping the selected example subprocess.
- Viewing subprocess logs in near real time.

Only one managed process runs at a time. Stop the running process before starting another one.
