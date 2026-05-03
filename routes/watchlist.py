"""Watchlist blueprint — personal and shared watchlists."""
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session
from flask_login import current_user, login_required

from database import (
    add_to_watchlist,
    get_or_create_personal_watchlist,
    get_or_create_shared_watchlist,
    get_user_by_id,
    get_watchlist_items,
    remove_from_watchlist,
)
from services import tmdb_service
from utils import clean_and_capitalize_name, clean_and_format

watchlist_bp = Blueprint("watchlist", __name__)

_NO_POSTER = "https://via.placeholder.com/200x300?text=No+Poster"

@watchlist_bp.route("/watchlist", methods=["GET"])
@login_required
def personal_watchlist():
    # Get or create the personal watchlist
    wl = get_or_create_personal_watchlist(current_user.id)
    items = []
    if wl:
        items = get_watchlist_items(wl['id'])
        
    return render_template("watchlist.html", items=items, is_shared=False, session=session)

@watchlist_bp.route("/watchlist/shared/<int:friend_id>", methods=["GET"])
@login_required
def shared_watchlist(friend_id):
    # Verify friend exists
    friend = get_user_by_id(friend_id)
    if not friend:
        flash("User not found.", "error")
        return redirect("/friends")
        
    wl = get_or_create_shared_watchlist(current_user.id, friend_id)
    items = []
    if wl:
        items = get_watchlist_items(wl['id'])
        
    return render_template(
        "watchlist.html", 
        items=items, 
        is_shared=True, 
        friend_username=friend[0]['username'], 
        friend_id=friend_id,
        session=session
    )

@watchlist_bp.route("/watchlist/add", methods=["POST"])
@login_required
def add_item():
    try:
        title = clean_and_format(request.form.get("title", ""))
        manual_director = request.form.get("director", "").strip()
        year = request.form.get("year", "")
        tv_show = request.form.get("tv", "0")
        friend_id = request.form.get("friend_id") # If provided, it's a shared watchlist
        
        if manual_director:
            manual_director = clean_and_capitalize_name(manual_director)

        if tv_show == "1":
            details = tmdb_service.get_tv_details(title, year, 1, manual_director)
        else:
            details = tmdb_service.get_movie_details(title, year, manual_director)

        if details:
            poster = details["poster"]
            director = details["director"]
            title = details["title"]
        else:
            poster = _NO_POSTER
            director = manual_director or "Unknown"

        # Determine which watchlist to add to
        if friend_id:
            wl = get_or_create_shared_watchlist(current_user.id, int(friend_id))
            redirect_url = f"/watchlist/shared/{friend_id}"
        else:
            wl = get_or_create_personal_watchlist(current_user.id)
            redirect_url = "/watchlist"

        if wl:
            add_to_watchlist(wl['id'], current_user.id, title, director, year, poster)
            flash("Added to watchlist!", "success")
        else:
            flash("Error accessing watchlist", "error")
            
        return redirect(redirect_url)
    except Exception as e:
        from flask import current_app
        current_app.logger.exception("Error adding to watchlist")
        flash("Something went wrong", "error")
        friend_id = request.form.get("friend_id")
        return redirect(f"/watchlist/shared/{friend_id}" if friend_id else "/watchlist")

@watchlist_bp.route("/watchlist/remove", methods=["POST"])
@login_required
def remove_item():
    item_id = request.form.get("item_id")
    friend_id = request.form.get("friend_id") # to know where to redirect
    
    if item_id:
        remove_from_watchlist(item_id)
        flash("Removed from watchlist", "success")
        
    if friend_id:
        return redirect(f"/watchlist/shared/{friend_id}")
    return redirect("/watchlist")
