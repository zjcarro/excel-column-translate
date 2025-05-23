import streamlit as st
import pandas as pd
from deep_translator import GoogleTranslator
import io
import json
from typing import Dict, Union, Any

# Initialize translator once
translator = GoogleTranslator(source='auto', target='en')

# In-memory translation cache
translation_cache = {}

def translate_text(text: str, tracker=None) -> str:
    if pd.isna(text) or text.strip() == "":
        return text  # Skip empty or whitespace-only headers
    if text in translation_cache:
        if tracker:
            tracker.progress(tracker.progress_value + 1)
        return translation_cache[text]
    try:
        result = translator.translate(str(text))
        translation_cache[text] = result
        if tracker:
            tracker.progress(tracker.progress_value + 1)
        return result
    except Exception as e:
        st.warning(f"Could not translate '{text}': {str(e)}")
        if tracker:
            tracker.progress(tracker.progress_value + 1)
        return text

def deduplicate_columns(columns):
    seen = {}
    result = []
    for col in columns:
        if col not in seen:
            seen[col] = 1
            result.append(col)
        else:
            seen[col] += 1
            result.append(f"{col}.{seen[col] - 1}")
    return result

def deduplicate_sheet_names(sheet_names):
    seen = {}
    result = []
    for sheet_name in sheet_names:
        if sheet_name not in seen:
            seen[sheet_name] = 1
            result.append(sheet_name)
        else:
            seen[sheet_name] += 1
            result.append(f"{sheet_name}.{seen[sheet_name] - 1}")
    return result

def remove_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Remove columns with empty or "Unnamed" headers
    df = df.loc[:, ~df.columns.str.startswith('Unnamed')]
    df = df.loc[:, df.columns.str.strip() != ""]
    return df

class ProgressTracker:
    def __init__(self, total):
        self.total = total
        self.progress_value = 0

    def progress(self, value):
        self.progress_value = value

def translate_columns(df: pd.DataFrame, translation_map: Dict[str, str], sheet_name: str, sheet_idx: int, total_sheets: int, overall_tracker) -> pd.DataFrame:
    # Remove empty/unnamed columns first
    df = remove_empty_columns(df)

    translated_columns = []
    total_columns = len(df.columns)

    # Display sheet name and column count
    progress_text = st.empty()
    progress_bar = st.progress(0)
    progress_text.write(f"Translating sheet {sheet_idx + 1}/{total_sheets}: '{sheet_name}' | {total_columns} columns")

    class ColumnProgressTracker:
        def __init__(self, total):
            self.total = total
            self.progress_value = 0

        def progress(self, value):
            self.progress_value = value
            progress_bar.progress(value / self.total)

    tracker = ColumnProgressTracker(total_columns)
    for col in df.columns:
        if col in translation_map:
            translated_columns.append(translation_map[col])
            tracker.progress(tracker.progress_value + 1)
        else:
            translated_columns.append(translate_text(col, tracker))
    progress_text.empty()
    progress_bar.empty()

    # Deduplicate
    translated_columns = deduplicate_columns(translated_columns)
    df.columns = translated_columns

    # Update overall progress
    overall_tracker.progress(overall_tracker.progress_value + total_columns)
    return df

def csv_to_json(
    csv_input: Union[str, io.BytesIO, pd.DataFrame],
    orient: str = "records",
    indent: int = 4,
    force_ascii: bool = False
) -> Union[Dict[str, Any], list]:
    """
    Convert CSV data to JSON using Pandas.
    Args:
        csv_input: Can be a file path (str), file-like object (BytesIO), or DataFrame.
        orient: JSON format ('records', 'split', 'index', 'columns', 'values').
        indent: JSON indentation (set to None for compact JSON).
        force_ascii: Escape non-ASCII characters if True.
    Returns:
        JSON-compatible dict/list (or raises ValueError on failure).
    """
    try:
        # Read CSV (handles both file paths and file-like objects)
        if isinstance(csv_input, pd.DataFrame):
            df = csv_input
        else:
            df = pd.read_csv(csv_input)
        
        # Convert to JSON-serializable object
        if orient == "records":
            json_data = json.loads(df.to_json(orient=orient, indent=indent, force_ascii=force_ascii))
        else:
            json_data = df.to_dict(orient=orient)
        
        return json_data
    
    except Exception as e:
        raise ValueError(f"CSV-to-JSON conversion failed: {str(e)}")

def process_excel_file(uploaded_file: Union[io.BytesIO, str], translation_map: Dict[str, str]) -> Dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(uploaded_file)
    total_sheets = len(xls.sheet_names)
    total_columns = sum(len(pd.read_excel(xls, sheet_name=sheet).columns) for sheet in xls.sheet_names)

    translated_sheets = {}
    translated_sheet_names = {}  # Store translated sheet names
    overall_progress_text = st.empty()
    overall_progress_bar = st.progress(0)
    overall_tracker = ProgressTracker(total_columns)
    overall_progress_text.write(f"Overall progress: 0/{total_sheets} sheets, 0/{total_columns} columns")

    # Translate sheet names
    sheet_translation_progress = st.empty()
    sheet_translation_progress.write("Translating sheet names...")
    sheet_translation_progress_bar = st.progress(0)
    for idx, sheet_name in enumerate(xls.sheet_names):
        translated_sheet_name = translate_text(sheet_name)
        translated_sheet_names[sheet_name] = translated_sheet_name
        sheet_translation_progress_bar.progress((idx + 1) / total_sheets)
    sheet_translation_progress.empty()
    sheet_translation_progress_bar.empty()

    # Deduplicate translated sheet names
    translated_sheet_names_list = list(translated_sheet_names.values())
    translated_sheet_names_list = deduplicate_sheet_names(translated_sheet_names_list)
    translated_sheet_names = {sheet: translated_name for sheet, translated_name in zip(xls.sheet_names, translated_sheet_names_list)}

    for sheet_idx, sheet_name in enumerate(xls.sheet_names):
        translated_sheet_name = translated_sheet_names[sheet_name]
        df = pd.read_excel(xls, sheet_name=sheet_name)
        translated_df = translate_columns(df, translation_map, translated_sheet_name, sheet_idx, total_sheets, overall_tracker)
        translated_sheets[translated_sheet_name] = translated_df
        overall_progress_text.write(
            f"Overall progress: {sheet_idx + 1}/{total_sheets} sheets, {overall_tracker.progress_value}/{total_columns} columns"
        )
        overall_progress_bar.progress(overall_tracker.progress_value / total_columns)
    overall_progress_text.empty()
    overall_progress_bar.empty()
    return translated_sheets

def process_csv_file(uploaded_file: Union[io.BytesIO, str], translation_map: Dict[str, str]) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file)
    total_columns = len(df.columns)

    overall_progress_text = st.empty()
    overall_progress_bar = st.progress(0)
    overall_tracker = ProgressTracker(total_columns)
    overall_progress_text.write(f"Overall progress: 0/{total_columns} columns")

    translated_df = translate_columns(df, translation_map, "CSV", 0, 1, overall_tracker)
    overall_progress_text.write(f"Overall progress: {overall_tracker.progress_value}/{total_columns} columns")
    overall_progress_bar.progress(overall_tracker.progress_value / total_columns)
    overall_progress_text.empty()
    overall_progress_bar.empty()
    return translated_df

def to_excel(translated_sheets: Dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in translated_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()

def main():
    st.set_page_config(page_title="Column Translator + CSV/JSON Converter")
    st.title("📊 Column Translator + CSV/JSON Converter")
    st.markdown("""
    Upload an Excel or CSV file to:
    1. Translate column headers/sheet names to English
    2. Convert CSV files to JSON
    """)

    # Initialize session state
    if 'translated_sheets' not in st.session_state:
        st.session_state.translated_sheets = None
    if 'translated_csv' not in st.session_state:
        st.session_state.translated_csv = None
    if 'json_data' not in st.session_state:
        st.session_state.json_data = None

    uploaded_file = st.file_uploader("Choose a file", type=['xlsx', 'xls', 'csv'])

    if uploaded_file is not None:
        file_type = "excel" if uploaded_file.name.endswith(('.xlsx', '.xls')) else "csv"
        st.markdown(f"**Uploaded File Type:** {file_type.upper()}")

        # Buttons for actions
        col1, col2 = st.columns(2)
        with col1:
            translate_clicked = st.button("🔤 Translate Headers")
        with col2:
            json_clicked = st.button("🧾 Convert to JSON (CSV only)")

        custom_translations = {}

        if translate_clicked:
            try:
                if file_type == "excel":
                    st.session_state.translated_sheets = process_excel_file(uploaded_file, custom_translations)
                    sheet_to_preview = st.selectbox("Select sheet to preview", list(st.session_state.translated_sheets.keys()))
                    st.dataframe(st.session_state.translated_sheets[sheet_to_preview].head())

                    excel_data = to_excel(st.session_state.translated_sheets)
                    st.download_button(
                        label="Download translated Excel file",
                        data=excel_data,
                        file_name="translated_headers.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                elif file_type == "csv":
                    st.session_state.translated_csv = process_csv_file(uploaded_file, custom_translations)
                    st.dataframe(st.session_state.translated_csv.head())

                    csv_data = st.session_state.translated_csv.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download translated CSV",
                        data=csv_data,
                        file_name="translated_headers.csv",
                        mime="text/csv"
                    )

            except Exception as e:
                st.error(f"An error occurred during translation: {str(e)}")

        if json_clicked:
            try:
                if file_type == "csv":
                    # Use original file for JSON conversion
                    st.session_state.json_data = csv_to_json(uploaded_file)
                    st.json(st.session_state.json_data)

                    json_str = json.dumps(st.session_state.json_data, indent=2)
                    st.download_button(
                        label="Download as JSON",
                        data=json_str,
                        file_name="converted.json",
                        mime="application/json"
                    )
                else:
                    st.warning("JSON conversion is only supported for CSV files.")
            except Exception as e:
                st.error(f"An error occurred during JSON conversion: {str(e)}")


if __name__ == "__main__":
    main()