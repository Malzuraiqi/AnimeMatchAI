# 🌸 AnimeMatchAI

An intelligent anime discovery tool that uses **Google Gemini AI** to bridge the gap between your watch history and your "Plan to Watch" list. Instead of generic suggestions, this app analyzes your specific feedback on random titles to find the high-scoring gems already waiting in your list.

---

## ✨ Features

* **AniList Integration:** Connects directly to your AniList profile to fetch your real Completed and Planning collections.
* **Active Learning:** Rate 10 random anime from your history to teach the AI your specific taste and current mood.
* **Strict Feedback:** Encourages concise, 10-word-or-less reasoning to ensure the AI focuses on the most important parts of your preferences.
* **Custom AI Logic:** Predicts a score for your planning list items and provides detailed reasoning for why they match your taste.
* **Session-Based:** Your data is cached temporarily for your session, keeping your AniList profile secure.

---

## 🛠️ Tech Stack

* **Backend:** Python / Flask
* **AI Engine:** Google Gemini API
* **Data Source:** AniList GraphQL API v2
* **Frontend:** HTML5, CSS3, JavaScript (Fetch API)

---

## 🤖 How It Works

1. **Search:** Enter your AniList username to pull your anime data.
2. **Rate:** The app selects 10 random shows you’ve completed. Give them a score and a quick reason why you liked (or hated) them.
3. **Analyze:** Your ratings and descriptions are sent to Gemini, which cross-references them with your Planning list.
4. **Recommend:** The AI returns the **Top** anime from your planning list that you are most likely to rate an 8/10 or higher.

---

## 🤝 Credits

* **Anime Data:** Powered by [AniList](https://anilist.co/).
* **AI Recommendations:** Powered by [Google Gemini](https://aistudio.google.com/).