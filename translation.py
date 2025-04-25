import streamlit as st
import pandas as pd
from deep_translator import GoogleTranslator
import io
from typing import Dict, Union

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

def process_excel_file(uploaded_file: Union[io.BytesIO, str], translation_map: Dict[str, str]) -> Dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(uploaded_file)
    total_sheets = len(xls.sheet_names)
    total_columns = sum(len(pd.read_excel(xls, sheet_name=sheet).columns) for sheet in xls.sheet_names)

    translated_sheets = {}
    overall_progress_text = st.empty()
    overall_progress_bar = st.progress(0)
    overall_tracker = ProgressTracker(total_columns)
    overall_progress_text.write(f"Overall progress: 0/{total_sheets} sheets, 0/{total_columns} columns")

    for sheet_idx, sheet_name in enumerate(xls.sheet_names):
        df = pd.read_excel(xls, sheet_name=sheet_name)
        translated_df = translate_columns(df, translation_map, sheet_name, sheet_idx, total_sheets, overall_tracker)
        translated_sheets[sheet_name] = translated_df
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
    st.title("📊 Column Header Translator")
    st.markdown("""
    Upload an Excel or CSV file to translate all column headers to English.
    You can optionally provide your own translations for specific columns.
    """)

    # Initialize session state for caching
    if 'translated_sheets' not in st.session_state:
        st.session_state.translated_sheets = None
    if 'translated_csv' not in st.session_state:
        st.session_state.translated_csv = None

    uploaded_file = st.file_uploader("Choose a file", type=['xlsx', 'xls', 'csv'])

    # st.subheader("Custom Translations (Optional)")
    # st.markdown("Specify your own translations for specific columns if needed.")
    custom_translations = {}
    # col1, col2 = st.columns(2)
    # for i in range(5):
    #     with col1:
    #         original = st.text_input(f"Original Column {i+1}", key=f"orig_{i}")
    #     with col2:
    #         translated = st.text_input(f"Translated to English {i+1}", key=f"trans_{i}")
    #     if original and translated:
    #         custom_translations[original] = translated

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(('.xlsx', '.xls')):
                # Process Excel file only if it hasn't been processed yet
                if st.session_state.translated_sheets is None:
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
            elif uploaded_file.name.endswith('.csv'):
                # Process CSV file only if it hasn't been processed yet
                if st.session_state.translated_csv is None:
                    st.session_state.translated_csv = process_csv_file(uploaded_file, custom_translations)
                st.dataframe(st.session_state.translated_csv.head())
                csv_data = st.session_state.translated_csv.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download translated CSV file",
                    data=csv_data,
                    file_name="translated_headers.csv",
                    mime="text/csv"
                )
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()