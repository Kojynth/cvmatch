@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "NO_PAUSE="
set "SKIP_LLM="
set "AI_MODE="
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--nopause" set "NO_PAUSE=1"
if /I "%~1"=="--skip-llm" set "SKIP_LLM=1"
if /I "%~1"=="--mode" goto :parse_mode
shift
goto parse_args
:parse_mode
if "%~2"=="" goto args_done
set "AI_MODE=%~2"
shift
shift
goto parse_args
:args_done

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%"
cd /d "%PROJECT_ROOT%"

if not "%AI_MODE%"=="" goto :ai_mode_ready
if not "%CVMATCH_AI_MODE%"=="" set "AI_MODE=%CVMATCH_AI_MODE%"
:ai_mode_ready
if "%AI_MODE%"=="" set "AI_MODE=lite"

set "LOG_DIR=%PROJECT_ROOT%logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_STAMP="
for /f %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "LOG_STAMP=%%a"
if not "%LOG_STAMP%"=="" goto :log_stamp_done
set "LOG_STAMP=%date%_%time%"
set "LOG_STAMP=%LOG_STAMP:/=-%"
set "LOG_STAMP=%LOG_STAMP::=-%"
set "LOG_STAMP=%LOG_STAMP:,=-%"
set "LOG_STAMP=%LOG_STAMP:.=-%"
set "LOG_STAMP=%LOG_STAMP: =0%"
:log_stamp_done
set "INSTALL_LOG=%LOG_DIR%\\installation_cvmatch_ai_%LOG_STAMP%.log"
echo CVMatch - AI Model Installer > "%INSTALL_LOG%"
echo Logs: %INSTALL_LOG% >> "%INSTALL_LOG%"
echo Logs: %INSTALL_LOG%

for %%I in ("%PROJECT_ROOT%") do (
    set "PROJECT_ROOT_PATH=%%~pI"
)
if "%PROJECT_ROOT_PATH%"=="\" goto :unsafe_project_root

set "CACHE_DIR=%PROJECT_ROOT%.hf_cache"
if not "%CVMATCH_HF_CACHE%"=="" set "CACHE_DIR=%CVMATCH_HF_CACHE%"
set "HUGGINGFACE_HUB_CACHE=%CACHE_DIR%"
set "HF_HUB_CACHE=%CACHE_DIR%"
set "TRANSFORMERS_CACHE=%CACHE_DIR%"
set "HF_HUB_DISABLE_SYMLINKS=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

set "VENV_PY=%PROJECT_ROOT%cvmatch_env\Scripts\python.exe"
set "PYTHON_CMD="
set "PYTHON_ARGS="
if exist "%VENV_PY%" (
    set "PYTHON_CMD=%VENV_PY%"
) else (
    if exist "%PROJECT_ROOT%python.exe" goto :python_hijack
    if exist "%PROJECT_ROOT%python.bat" goto :python_hijack
    if exist "%PROJECT_ROOT%python.cmd" goto :python_hijack
    set "PYTHON_BAD_VERSION="
    set "PYTHON_BAD_ARCH="
    set "HAS_PY_LAUNCHER="
    where py >nul 2>&1
    if not errorlevel 1 set "HAS_PY_LAUNCHER=1"
    if not "%CVMATCH_PYTHON%"=="" (
        call :validate_python "%CVMATCH_PYTHON%"
        if not defined PYTHON_CMD (
            echo [WARN] CVMATCH_PYTHON invalide - detection automatique. >> "%INSTALL_LOG%"
            echo [WARN] CVMATCH_PYTHON invalide - detection automatique.
        )
    )
    if not defined PYTHON_CMD (
        call :find_python_from_py "3.13"
        call :find_python_from_py "3.12"
        call :find_python_from_py "3.11"
        call :find_python_from_py "3.10"
        call :find_python_from_py "3.14"
    )
    if not defined PYTHON_CMD (
        for /f "delims=" %%a in ('where python 2^>nul') do call :validate_python "%%a"
    )
    if not defined PYTHON_CMD (
        if defined PYTHON_BAD_VERSION goto :python_version
        if defined PYTHON_BAD_ARCH goto :python_arch
        goto :no_python
    )
)
set "REQ_AI_FILE=%PROJECT_ROOT%requirements_ai_windows.txt"
if not exist "%REQ_AI_FILE%" set "REQ_AI_FILE=%PROJECT_ROOT%requirements_windows.txt"
if not exist "%REQ_AI_FILE%" goto :req_ai_missing
set "REQ_AI_LOCK=%PROJECT_ROOT%requirements_ai_windows.lock"
if /I "%REQ_AI_FILE%"=="%PROJECT_ROOT%requirements_windows.txt" set "REQ_AI_LOCK=%PROJECT_ROOT%requirements_windows.lock"

set "LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct"
set "LLM_PROFILE_ID=qwen2-0.5b"
if not "%CVMATCH_LLM_MODEL_ID%"=="" set "LLM_MODEL_ID=%CVMATCH_LLM_MODEL_ID%"
if not "%CVMATCH_LLM_PROFILE_ID%"=="" set "LLM_PROFILE_ID=%CVMATCH_LLM_PROFILE_ID%"

set "INSTALL_LLM=1"
if defined SKIP_LLM set "INSTALL_LLM="
if /I "%CVMATCH_SKIP_LLM%"=="1" set "INSTALL_LLM="
if /I "%AI_MODE%"=="base-only" set "INSTALL_LLM="
if /I "%AI_MODE%"=="llm-only" set "INSTALL_LLM=1"

if exist "%CACHE_DIR%" goto :cache_ready
echo Creating cache directory "%CACHE_DIR%"...
echo Creating cache directory "%CACHE_DIR%"... >> "%INSTALL_LOG%"
mkdir "%CACHE_DIR%" >nul 2>&1
:cache_ready

echo === CVMatch AI Model Installer ===
echo === CVMatch AI Model Installer === >> "%INSTALL_LOG%"
echo Mode: %AI_MODE% >> "%INSTALL_LOG%"
echo Cache: %CACHE_DIR% >> "%INSTALL_LOG%"
echo Python: %PYTHON_CMD% %PYTHON_ARGS% >> "%INSTALL_LOG%"

"%PYTHON_CMD%" %PYTHON_ARGS% -c "import google.protobuf, sentencepiece" >nul 2>&1
if errorlevel 1 goto :deps_install
goto :deps_done

:deps_install
echo Installing missing Python dependencies: protobuf, sentencepiece...
echo Installing missing Python dependencies: protobuf, sentencepiece... >> "%INSTALL_LOG%"
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --upgrade protobuf sentencepiece >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 goto :deps_failed
goto :deps_done

:deps_failed
echo.
echo [ERROR] Failed to install required Python dependencies.
echo Please run: "%PYTHON_CMD%" %PYTHON_ARGS% -m pip install protobuf sentencepiece
echo [ERROR] Failed to install required Python dependencies. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:deps_done

rem Ensure AI python dependencies (torch/transformers/huggingface_hub)
set "TORCH_CPU_INDEX=https://download.pytorch.org/whl/cpu"
set "TORCH_CUDA_INDEXES=https://download.pytorch.org/whl/cu131 https://download.pytorch.org/whl/cu128 https://download.pytorch.org/whl/cu126 https://download.pytorch.org/whl/cu124 https://download.pytorch.org/whl/cu121"
set "HAS_NVIDIA_GPU="
where nvidia-smi >nul 2>&1
if not errorlevel 1 set "HAS_NVIDIA_GPU=1"

"%PYTHON_CMD%" %PYTHON_ARGS% -c "import torch, transformers, huggingface_hub" >nul 2>&1
if errorlevel 1 goto :install_ai_deps
if defined HAS_NVIDIA_GPU goto :check_torch_cuda
goto :ai_deps_done

:check_torch_cuda
"%PYTHON_CMD%" %PYTHON_ARGS% -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 2)" >nul 2>&1
if errorlevel 2 goto :install_ai_deps
goto :ai_deps_done

:install_ai_deps
echo Installing AI Python dependencies...
echo Installing AI Python dependencies... >> "%INSTALL_LOG%"
if defined HAS_NVIDIA_GPU goto :install_torch_cuda
call :INSTALL_TORCH "%TORCH_CPU_INDEX%"
if errorlevel 1 goto :ai_deps_failed
goto :torch_done

:install_torch_cuda
call :TRY_CUDA_TORCH
if errorlevel 1 goto :torch_cpu_fallback
goto :torch_done

:torch_cpu_fallback
echo [WARN] CUDA PyTorch install failed - falling back to CPU build.
echo [WARN] CUDA PyTorch install failed - falling back to CPU build. >> "%INSTALL_LOG%"
call :INSTALL_TORCH "%TORCH_CPU_INDEX%"
if errorlevel 1 goto :ai_deps_failed

:torch_done
set "REQ_AI_TARGET=%REQ_AI_FILE%"
set "REQ_AI_HASH_ARGS="
if exist "%REQ_AI_LOCK%" (
    set "REQ_AI_TARGET=%REQ_AI_LOCK%"
    set "REQ_AI_HASH_ARGS=--require-hashes"
    echo Using locked requirements file. >> "%INSTALL_LOG%"
) else (
    echo [WARN] Using unpinned requirements file. >> "%INSTALL_LOG%"
    echo [WARN] Consider creating requirements_ai_windows.lock with hashes.
)
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install %REQ_AI_HASH_ARGS% -r "%REQ_AI_TARGET%" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 goto :ai_deps_failed
goto :ai_deps_done

:ai_deps_done

rem Optional: install llama.cpp (GGUF runner) for local generation via llama-server.
set "LLAMA_DIR=%PROJECT_ROOT%tools\llama.cpp"
if exist "%LLAMA_DIR%" goto :llama_dir_ready
mkdir "%LLAMA_DIR%" >nul 2>&1
:llama_dir_ready
echo Installing llama.cpp - llama-server into "%LLAMA_DIR%"...
echo Installing llama.cpp - llama-server into "%LLAMA_DIR%"... >> "%INSTALL_LOG%"
"%PYTHON_CMD%" %PYTHON_ARGS% "%PROJECT_ROOT%scripts\install_llama_cpp.py" --dest-dir "%LLAMA_DIR%" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 goto :llama_warn
goto :llama_done

:llama_warn
echo [WARN] llama.cpp install failed - you can install it manually later.
echo [WARN] llama.cpp install failed - you can install it manually later. >> "%INSTALL_LOG%"
echo        Tip: set CVMATCH_LLAMA_CPP_BINARY and CVMATCH_LLAMA_CPP_MODEL_PATH if needed.
echo        Tip: set CVMATCH_LLAMA_CPP_BINARY and CVMATCH_LLAMA_CPP_MODEL_PATH if needed. >> "%INSTALL_LOG%"

:llama_done

echo Downloading AI models...
echo Downloading AI models... >> "%INSTALL_LOG%"
if defined INSTALL_LLM goto :download_llm
goto :download_base

:download_llm
echo LLM model: %LLM_MODEL_ID%
echo LLM model: %LLM_MODEL_ID% >> "%INSTALL_LOG%"
"%PYTHON_CMD%" %PYTHON_ARGS% "%PROJECT_ROOT%scripts\download_ai_models.py" --cache-dir "%CACHE_DIR%" --mode "%AI_MODE%" --include-llm --llm-model "%LLM_MODEL_ID%" >> "%INSTALL_LOG%" 2>&1
goto :download_done

:download_base
"%PYTHON_CMD%" %PYTHON_ARGS% "%PROJECT_ROOT%scripts\download_ai_models.py" --cache-dir "%CACHE_DIR%" --mode "%AI_MODE%" >> "%INSTALL_LOG%" 2>&1

:download_done
if errorlevel 401 goto :unauthorized
if errorlevel 1 goto :error

if defined INSTALL_LLM goto :set_model
goto :after_set_model

:set_model
echo Setting default LLM profile: %LLM_PROFILE_ID%
echo Setting default LLM profile: %LLM_PROFILE_ID% >> "%INSTALL_LOG%"
"%PYTHON_CMD%" %PYTHON_ARGS% "%PROJECT_ROOT%scripts\set_default_model.py" --model-id "%LLM_PROFILE_ID%" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 goto :set_model_warn
goto :after_set_model

:set_model_warn
echo [WARN] Could not set default model configuration. You can choose a model in Settings later.
echo [WARN] Could not set default model configuration. You can choose a model in Settings later. >> "%INSTALL_LOG%"

:after_set_model

echo.
echo AI model cache ready in "%CACHE_DIR%"
echo AI model cache ready in "%CACHE_DIR%" >> "%INSTALL_LOG%"
echo You can now run CVMatch with AI extraction enabled.
echo You can now run CVMatch with AI extraction enabled. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 0

:find_python_from_py
if defined PYTHON_CMD exit /b 0
if not defined HAS_PY_LAUNCHER exit /b 0
set "PY_TAG=%~1"
py -%PY_TAG% -c "import struct, sys; sys.exit(0 if struct.calcsize('P')*8 >= 64 else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PYTHON_CMD=py"
set "PYTHON_ARGS=-%PY_TAG%"
exit /b 0

:validate_python
if defined PYTHON_CMD exit /b 0
set "CANDIDATE=%~1"
if "%CANDIDATE%"=="" exit /b 0
if not exist "%CANDIDATE%" exit /b 0
echo("%CANDIDATE%" | findstr /I /L /C:"WindowsApps" >nul
if not errorlevel 1 exit /b 0
"%CANDIDATE%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    set "PYTHON_BAD_VERSION=1"
    exit /b 0
)
"%CANDIDATE%" -c "import struct; sys.exit(0 if struct.calcsize('P')*8 >= 64 else 1)" >nul 2>&1
if errorlevel 1 (
    set "PYTHON_BAD_ARCH=1"
    exit /b 0
)
set "PYTHON_CMD=%CANDIDATE%"
set "PYTHON_ARGS="
exit /b 0

:ai_deps_failed
echo.
echo [ERROR] Failed to install AI dependencies.
echo Please verify your Python environment and re-run installation_cvmatch_ai_windows.bat.
echo [ERROR] Failed to install AI dependencies. >> "%INSTALL_LOG%"
echo Please verify your Python environment and re-run installation_cvmatch_ai_windows.bat. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:unsafe_project_root
echo.
echo [ERROR] Unsafe project root path detected.
echo [ERROR] Unsafe project root path detected. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:python_hijack
echo.
echo [ERROR] Local python executable detected in project directory.
echo [ERROR] Local python executable detected in project directory. >> "%INSTALL_LOG%"
echo Remove python.exe/python.bat/python.cmd and re-run the installer.
echo Remove python.exe/python.bat/python.cmd and re-run the installer. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:python_version
echo.
echo [ERROR] Python 3.10+ required.
echo [ERROR] Python 3.10+ required. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:python_arch
echo.
echo [ERROR] Python 64-bit required.
echo [ERROR] Python 64-bit required. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:no_python
echo.
echo [ERROR] Python not found on PATH.
echo [ERROR] Python not found on PATH. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:req_ai_missing
echo.
echo [ERROR] requirements file missing (AI or Windows).
echo [ERROR] requirements file missing (AI or Windows). >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1

:TRY_CUDA_TORCH
for %%I in (%TORCH_CUDA_INDEXES%) do (
    echo Attempting PyTorch CUDA via %%I...
    echo Attempting PyTorch CUDA via %%I... >> "%INSTALL_LOG%"
    call :INSTALL_TORCH "%%I"
    if errorlevel 1 (
        echo [WARN] PyTorch CUDA failed via %%I
        echo [WARN] PyTorch CUDA failed via %%I >> "%INSTALL_LOG%"
    ) else (
        echo [OK] PyTorch CUDA installed via %%I
        echo [OK] PyTorch CUDA installed via %%I >> "%INSTALL_LOG%"
        exit /b 0
    )
)
exit /b 1

:INSTALL_TORCH
set "TORCH_INDEX_URL=%~1"
if "%TORCH_INDEX_URL%"=="" set "TORCH_INDEX_URL=%TORCH_CPU_INDEX%"
"%PYTHON_CMD%" %PYTHON_ARGS% -m pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url %TORCH_INDEX_URL% >> "%INSTALL_LOG%" 2>&1
exit /b %ERRORLEVEL%

:unauthorized
echo.
echo [ERROR] Authentication required to download models.
echo Run "huggingface-cli login" and re-run this script.
echo [ERROR] Authentication required to download models. >> "%INSTALL_LOG%"
echo Run "huggingface-cli login" and re-run this script. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 401

:error
echo.
echo Failed to download one or more models.
echo Verify your internet connection and that huggingface_hub is installed.
echo Failed to download one or more models. >> "%INSTALL_LOG%"
echo Verify your internet connection and that huggingface_hub is installed. >> "%INSTALL_LOG%"
if not defined NO_PAUSE pause
endlocal
exit /b 1
