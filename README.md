# Kineto

Kineto is an open-source Flask web app to track watched movies and TV shows, browse stats, and explore recommendations.

Live app: [https://lista-film-v2.onrender.com](https://lista-film-v2.onrender.com)

## What It Does

- Track watched titles with rating, date, genre, and cinema/rewatch flags
- Monthly home view for current month watches
- Aggregated views by directors, genres, years, and ratings
- Personal and friend profile stats with charts
- Optional AI recommendation workflow in Discover

## Tech Stack

- Flask
- Supabase
- TMDB API
- Jinja templates
- Vanilla JavaScript and CSS

## Open Source Note

This repository is public as a real project/codebase reference.
It is not maintained as a strict reproducibility package.

## Run Locally (Optional)

If you want to try it locally:

1. Create a virtual environment and activate it

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

1. Install dependencies

```powershell
pip install -r requirements.txt
```

1. Create a `.env` file (you can copy from `.env.example`) and add your own keys/secrets

```powershell
Copy-Item .env.example .env
```

At minimum you will need values for Supabase, TMDB, Flask secret key, email password, and OPENROUTER_API_KEY (for Discover recommendations).

1. Run the app

```powershell
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Main Folders

- **app.py**: Flask routes, UI logic, integrations
- **database.py**: Supabase data access helpers
- **auth/**: authentication and password reset blueprints
- **templates/**: Jinja templates
- **static/**: CSS and JavaScript assets

## Credits

- [TMDB](https://www.themoviedb.org/?language=it-IT)
- [Frankslaboratory](https://www.youtube.com/@Frankslaboratory)
- [Fireship](https://www.youtube.com/@Fireship)
- [CSS - Tricks](https://css-tricks.com/)
