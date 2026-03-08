import py_compile

files = [
    'app/views/profile_details_editor.py',
    'app/views/template_preview_window.py',
    'app/views/extracted_data_viewer.py',
    'app/views/main_window.py',
]

for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print('OK', f)
    except Exception as e:
        print('FAIL', f, e)
