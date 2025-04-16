import matplotlib.pyplot as plt

# 데이터 설정
categories = ["k-pop", "pop"]
accuracies = [92, 80]
colors = ["blue", "red"]

# 막대 그래프 생성
fig, ax = plt.subplots()

bars = ax.bar(categories, accuracies, color=colors)

# 각 막대 위에 정확도 값(%) 텍스트 표시
for bar in bars:
    height = bar.get_height()
    ax.annotate(f'{height}%',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),  # 막대 위에서 3포인트 위쪽으로 이동
                textcoords="offset points",
                ha='center',
                va='bottom')

# y축 범위 설정
ax.set_ylim(0, 100)

# 축 제목 및 그래프 제목 설정
ax.set_xlabel("Song Category")
ax.set_ylabel("accuracy rate")
ax.set_title("Accuracy Comparison")

# 그래프 출력
plt.show()