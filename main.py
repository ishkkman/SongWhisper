#!/usr/bin/env python3
# ==============================================================================
# SongWhisper - 짧은 가사가 포함된 음성 녹음을 통해 매칭되는 노래를 찾아,
#                해당 노래의 검색 결과 페이지(예: YouTube)를 크롬 창으로 여는 프로그램
#
# 환경: Mac M1, Python 3.11, Visual Studio Code
#
# 주요 기능:
# 1. Tkinter GUI를 통해 녹음을 시작하고 종료하여, 음성 파일(WAV)을 저장
# 2. 녹음된 WAV 파일을 speech_recognition을 사용하여 음성 인식 (가사 추출)
# 3. 추출된 가사 텍스트를 기반으로 YouTube 검색 URL을 생성
# 4. Selenium을 사용하여 크롬 브라우저에서 해당 검색 결과 페이지를 열기
#
# 자동 재생이 반드시 필요하지 않으며, 사용자가 재생 버튼을 클릭해도 무방함.
# ==============================================================================

# ----- [1] 필수 모듈 임포트 -----
import tkinter as tk                              # GUI 생성을 위한 Tkinter
from tkinter import messagebox, simpledialog      # 경고창과 입력창을 위한 모듈
import sounddevice as sd                          # 마이크로부터 오디오 녹음을 위한 모듈
import numpy as np                                # 오디오 데이터 배열 및 수치 계산
import threading                                  # 녹음을 백그라운드 스레드로 실행 (GUI 유지)
import scipy.io.wavfile as wav                     # 녹음 데이터를 WAV 파일로 저장하기 위함
import datetime                                   # 파일명에 날짜/시간 정보를 추가하기 위함
import os                                         # 파일/디렉토리 관련 작업
import time                                       # 지연(sleep) 처리용
import requests                                   # HTTP 요청 (필요시 사용)

# Selenium 및 webdriver_manager (크롬 제어용)
from selenium import webdriver                    # Selenium WebDriver 기능
from selenium.webdriver.chrome.service import Service  # ChromeDriver 서비스
from webdriver_manager.chrome import ChromeDriverManager  # ChromeDriver 자동 설치
from selenium.webdriver.common.by import By       # 페이지 요소 선택용

# 음성 인식을 위한 speech_recognition 모듈
import speech_recognition as sr                   # 음성인식(Speech-to-Text) 기능

# ----- [2] 전역 변수 설정 -----
fs = 44100                                       # 녹음 샘플링 속도 (Hz)
recording = False                                # 녹음 진행 여부 플래그
audio_chunks = []                                # 녹음 도중 받은 오디오 데이터 청크를 저장할 리스트

# ----- [3] 녹음 및 파일 저장 함수 -----
def record_audio():
    """
    마이크 입력을 받아 실시간으로 audio_chunks 리스트에 데이터를 저장합니다.
    (백그라운드 스레드에서 실행되어 GUI가 멈추지 않도록 함)
    """
    global recording, audio_chunks
    recording = True                           # 녹음 시작 표시
    audio_chunks = []                          # 이전 녹음 데이터 초기화

    def callback(indata, frames, time_info, status):
        # 마이크로부터 입력된 데이터의 복사본을 audio_chunks에 추가
        if recording:
            audio_chunks.append(indata.copy())

    # sounddevice의 InputStream을 열어 마이크 데이터를 받아 저장
    with sd.InputStream(samplerate=fs, channels=1, callback=callback):
        while recording:
            sd.sleep(100)                      # 100ms마다 녹음 상태 확인

def stop_recording_and_save():
    """
    녹음을 중지하고, 저장된 audio_chunks를 하나의 WAV 파일로 저장합니다.
    파일명은 현재 날짜 및 시간 정보를 포함합니다.
    반환: 생성된 파일명 (문자열) 또는 데이터 없음(None)
    """
    global recording, audio_chunks
    recording = False                          # 녹음 중지
    time.sleep(0.5)                            # 녹음 스레드 종료 대기
    if audio_chunks:
        # 저장된 모든 청크를 하나의 NumPy 배열로 결합
        audio_data = np.concatenate(audio_chunks, axis=0)
        # 현재 날짜/시간 정보로 파일명 생성 (예: "20250408_153045.wav")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}.wav"
        # 오디오 데이터를 16비트 PCM 정수형으로 변환 후 WAV 파일로 저장
        wav.write(filename, fs, (audio_data * 32767).astype(np.int16))
        return filename
    return None

# ----- [4] 음성 인식 (Speech-to-Text) 함수 -----
def recognize_lyrics(file_path):
    """
    주어진 WAV 파일(file_path)을 로드하여, speech_recognition을 통해
    음성 인식을 수행하고, 텍스트(가사)를 추출합니다.
    반환: 인식된 텍스트 (문자열) 또는 빈 문자열("")
    """
    recognizer = sr.Recognizer()              # Recognizer 객체 생성
    # WAV 파일을 AudioFile로 로드
    with sr.AudioFile(file_path) as source:
        audio_data = recognizer.record(source)  # 전체 파일을 오디오 데이터로 읽음
    try:
        # Google Speech Recognition API를 사용하여 음성 인식 (한국어 설정)
        text = recognizer.recognize_google(audio_data, language="ko-KR")
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print("음성 인식 API 요청 오류:", e)
        return ""

# ----- [5] 인식 결과를 기반으로 YouTube 검색 URL 생성 함수 -----
def process_recognition_result(recognized_text):
    """
    인식된 텍스트(가사)를 바탕으로, 해당 텍스트를 검색어로 하여 YouTube 검색 URL을 생성합니다.
    반환: dict 형식으로 'song_url'과 'song_title'을 포함
    """
    # 만약 인식된 텍스트가 없다면 에러 메시지 반환
    if not recognized_text:
        return {"error": "가사를 인식하지 못했습니다."}
    import urllib.parse
    # URL 인코딩을 적용해 검색 쿼리 생성
    query = urllib.parse.quote_plus(recognized_text)
    song_url = f"https://www.youtube.com/results?search_query={query}"
    # 간단한 타이틀은 인식된 텍스트의 앞부분을 사용
    song_title = recognized_text[:50] + "..." if len(recognized_text) > 50 else recognized_text
    return {"song_url": song_url, "song_title": song_title}

# ----- [6] Selenium을 사용하여 브라우저에서 노래 검색 결과 페이지 열기 함수 -----
def open_song_with_selenium(song_url):
    """
    Selenium으로 YouTube 검색 결과 페이지(song_url)를 열고,
    첫 번째 Shorts 링크(/shorts/)를 찾아 클릭하여 자동 재생 시도.
    """
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    import time

    options = webdriver.ChromeOptions()
    # 로그인된 크롬 프로필을 사용할 수도 있고, 새 폴더 지정 등 유저 상황에 맞게 설정
    # 아래 경로에서 "jsh" 부분은 실제 Mac 사용자명으로 변경
    options.add_argument("user-data-dir=/Users/jsh/Library/Application Support/Google/Chrome")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    # (옵션) 자동화 배너 제거: 'Chrome이 자동화된...' 배너 숨기기
    # (버전에 따라 동작 안 할 수도 있음)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.get(song_url)
    time.sleep(5)  # 검색 결과 페이지 로딩 대기

    try:
        # 첫 번째 Shorts 링크 찾기 ("/shorts/"를 포함하는 <a> 태그 중 첫 번째)
        shorts_link = driver.find_element(
            By.XPATH,
            '(//a[contains(@href, "/shorts/")])[1]'
        )
        shorts_link.click()
        print("첫 번째 Shorts 링크 클릭 완료!")
    except Exception as e:
        print("Shorts 링크 클릭 실패:", e)
        # 필요하다면 fallback으로 일반 영상 클릭 로직 추가 가능
        # 여기서는 그냥 종료
        return driver
    
    # Shorts 페이지가 로드될 시간을 추가로 줍니다.
    time.sleep(5)

    # Shorts는 보통 로드하면 자동으로 재생되나, 혹시 안 될 경우에 대비해 아래 JS 호출 시도
    try:
        driver.execute_script("document.getElementsByTagName('video')[0].play()")
        print("JS로 video.play() 호출 완료!")
    except Exception as e:
        print("video.play() 호출 실패:", e)

    return driver

# ----- [7] Tkinter GUI 클래스 정의 -----
class SongWhisperApp:
    def __init__(self, master):
        self.master = master
        master.title("SongWhisper")
        
        # 메인 프레임 생성 및 여백 지정
        self.frame = tk.Frame(master)
        self.frame.pack(padx=10, pady=10)
        
        # 상태 메시지 레이블: 현재 상태, 지시 문구 표시
        self.status_label = tk.Label(self.frame, text="Start 버튼을 눌러 가사가 있는 노래 소절 녹음 시작")
        self.status_label.pack()
        
        # 녹음 시작 버튼
        self.start_button = tk.Button(self.frame, text="Start", command=self.start_recording)
        self.start_button.pack(pady=5)
        
        # 녹음 종료(완료) 버튼
        self.stop_button = tk.Button(self.frame, text="Done", command=self.stop_recording)
        self.stop_button.pack(pady=5)
        
        # 녹음된 파일 목록 표시용 Listbox
        self.file_listbox = tk.Listbox(self.frame, width=50)
        self.file_listbox.pack(pady=5)
        
        # 노래 찾기 버튼: 선택된 녹음 파일을 기반으로 음성 인식을 수행
        # 인식된 가사를 검색어로 하여 YouTube 검색 결과 페이지를 엽니다.
        self.find_song_button = tk.Button(self.frame, text="노래찾기", command=self.find_song)
        self.find_song_button.pack(pady=5)
        
        # 매칭된 노래 정보 표시용 레이블
        self.song_info_label = tk.Label(self.frame, text="매칭된 노래 정보가 여기에 표시됩니다.")
        self.song_info_label.pack(pady=5)
        
        # 프로그램 종료 버튼
        self.quit_button = tk.Button(self.frame, text="프로그램 종료", command=master.quit)
        self.quit_button.pack(pady=5)
        
        self.recording_thread = None

    def start_recording(self):
        """
        Start 버튼 클릭 시 호출.
        녹음 상태 메시지를 업데이트하고, 백그라운드 스레드에서 녹음을 시작합니다.
        """
        self.status_label.config(text="노래 소절을 불러주세요... 녹음 중입니다.")
        self.recording_thread = threading.Thread(target=record_audio, daemon=True)
        self.recording_thread.start()

    def stop_recording(self):
        """
        Done 버튼 클릭 시 호출.
        녹음을 중지하고, WAV 파일로 저장한 후, 파일명을 Listbox에 추가합니다.
        """
        filename = stop_recording_and_save()
        if filename:
            self.status_label.config(text=f"녹음 완료: {filename}")
            self.file_listbox.insert(tk.END, filename)
        else:
            self.status_label.config(text="녹음 데이터가 없습니다.")

    def find_song(self):
        """
        노래찾기 버튼 클릭 시, Listbox에서 선택된 녹음 파일을 대상으로
        Speech-to-Text 기능을 이용하여 가사를 추출한 후,
        추출된 텍스트로 YouTube 검색 URL을 생성하고, Selenium을 통해 페이지를 엽니다.
        """
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("경고", "녹음 파일을 선택하세요.")
            return
        
        selected_file = self.file_listbox.get(selected_indices[0])
        self.status_label.config(text="가사 인식 중...")
        
        # 음성 인식 함수를 사용하여 녹음 파일에서 가사를 추출
        recognized_text = recognize_lyrics(selected_file)
        print("인식된 가사:", recognized_text)  # 콘솔에 인식된 텍스트 출력
        if not recognized_text:
            self.status_label.config(text="가사 인식에 실패했습니다.")
            messagebox.showerror("오류", "가사를 인식하지 못했습니다. 다시 녹음해 주세요.")
            return
        
        # 추출된 가사를 기반으로 YouTube 검색 URL 생성
        processed = process_recognition_result(recognized_text)
        if "error" in processed:
            self.status_label.config(text=processed["error"])
            messagebox.showerror("오류", processed["error"])
            return
        
        song_url = processed["song_url"]
        song_title = processed["song_title"]
        self.song_info_label.config(text=f"매칭된 노래(검색어): {song_title}")
        
        # Selenium을 통해 해당 URL(검색 결과 페이지)를 크롬에서 엽니다.
        open_song_with_selenium(song_url)
        self.status_label.config(text="노래 검색 페이지가 열렸습니다.")

# ----- [8] 메인 실행부 -----
if __name__ == "__main__":
    root = tk.Tk()
    app = SongWhisperApp(root)
    root.mainloop()
