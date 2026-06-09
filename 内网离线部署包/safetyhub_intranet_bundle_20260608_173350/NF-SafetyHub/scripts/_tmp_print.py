from pathlib import Path

Path('/tmp/safetyhub_py_file_probe.txt').write_text('file_python_ran\n')
print('file_python_stdout_ok', flush=True)
