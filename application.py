import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use postgres database
db = SQL(os.environ.get("DATABASE_URL"))

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    if request.method == "GET":
        asset_total = 0
        cash = db.execute("SELECT cash FROM users WHERE id = :id",id=session["user_id"])
        rows = db.execute("SELECT symbol, company, shares FROM symbols JOIN shares ON id = symbol_id WHERE user_id = :id", id=session["user_id"])
        holdings = []

        for row in rows:
            print (row["shares"])
            if row["shares"] != 0 and row["shares"] != None:
                symbol = row["symbol"]
                name = row["company"]
                shares = row["shares"]
                quote = lookup(row["symbol"])
                price = quote["price"]
                value = price * shares
                asset_total += value
                holdings.append({"symbol":symbol, "name":name, "shares":shares, "price":usd(price), "value":usd(value)})

        total = usd(round(asset_total + cash[0]["cash"], 2))
        return render_template("index.html", holdings=holdings, total=total, cash=usd(round(cash[0]["cash"],2)))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")

    if request.method == "POST":

        stock = lookup(request.form.get("symbol"))
        shares = int(request.form.get("shares"))
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        transacted = datetime.datetime.now()

        if not request.form.get("symbol") or stock == None:
            return apology("invalid input", 403)

        elif cash[0]["cash"] < shares * stock["price"]:
            return apology("insufficient funds", 400)

        else:
            db.execute("INSERT OR IGNORE INTO symbols (company, symbol) VALUES (:company, :symbol)", company=stock["name"], symbol=stock["symbol"])

            db.execute("INSERT INTO portfolio (symbol_id, user_id, shares, transacted, price) VALUES ((SELECT id FROM symbols WHERE company = :company), :id, :shares, :transacted, :price)", company=stock["name"], id=session["user_id"], shares=shares, transacted=transacted, price=stock["price"])

            check = db.execute("SELECT COUNT(*) FROM shares WHERE user_id = :id AND symbol_id = (SELECT id FROM symbols WHERE symbol = :symbol)", id=session["user_id"], symbol=stock["symbol"])

            if check[0]["COUNT(*)"] == 1:
                db.execute("UPDATE shares SET shares = (SELECT SUM(shares) FROM portfolio WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = :symbol) AND user_id = :id) WHERE user_id = :id AND symbol_id = (SELECT id FROM symbols WHERE symbol = :symbol)", id=session["user_id"], symbol=stock["symbol"])
            else:
                db.execute("INSERT INTO shares (symbol_id, user_id, shares) VALUES ((SELECT id FROM symbols WHERE symbol = :symbol), :id, (SELECT SUM(shares) FROM portfolio WHERE symbol_id = (SELECT id FROM symbols WHERE symbol = :symbol) AND user_id = :id))", symbol=stock["symbol"], id=session["user_id"])

            db.execute("UPDATE users SET cash = cash - :shares * :stock WHERE id = :id", shares=shares, stock=stock["price"], id=session["user_id"])

            return redirect("/")

@app.route("/history")
@login_required
def history():

    if request.method == "GET":
        rows = db.execute("SELECT shares, price, transacted, symbol FROM portfolio JOIN symbols ON symbol_id = id WHERE user_id = :id", id=session["user_id"])
        for row in rows:
            row["price"] = usd(row["price"])
        return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    if request.method == "POST":
        stock = lookup(request.form.get("quote"))
        if stock == None:
            return apology("stock does not exist", 403)
        else:
            return render_template("quoted.html", symbol=stock["symbol"], name=stock["name"], price=stock["price"])

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":

        return render_template("register.html")

    if request.method == "POST":

        username = request.form.get("username")
        pw = request.form.get("password")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not pw:
            return apology("must provide password", 403)

        #Ensure password fields are the same
        elif pw != request.form.get("confirmation"):
            return apology("passwords do not match", 403)

        # Ensure username is not taken then register if available
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)
        if len(rows) == 1:
            return apology("username already exist", 403)
        else:
            password=generate_password_hash(pw)
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)", username=username, password=password)
            return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":

        symbols = db.execute("SELECT symbol FROM symbols")
        return render_template("sell.html", symbols=symbols)

    if request.method == "POST":

        if request.form['Cash out'] == 'Cash out':
            return render_template("jesus.html")

        if request.form['Cash out'] == 'Sell':

            symbol = request.form.get("symbol")
            shares = -1 * int(request.form.get("shares"))
            compare = int(request.form.get("shares"))
            price = lookup(request.form.get("symbol"))
            stock = db.execute("SELECT shares FROM shares WHERE user_id = :id AND symbol_id = (SELECT id FROM symbols WHERE symbol = :symbol)", id=session["user_id"], symbol=symbol)
            transacted = datetime.datetime.now()

            if symbol == None:
                return apology("Please select stock")

            elif stock[0]["shares"] == None:
                return apology("You do not own any shares")

            elif stock[0]["shares"] < compare:
                return apology("Sale exceeds current total of shares")

            else:
                db.execute("INSERT INTO portfolio (symbol_id, user_id, shares, transacted, price) VALUES ((SELECT id FROM symbols WHERE symbol = :symbol), :id, :shares, :transacted, :price)", symbol=symbol, id=session["user_id"], shares=shares, transacted=transacted, price=price["price"])
                db.execute("UPDATE shares SET shares = shares + :shares WHERE user_id = :id AND symbol_id = (SELECT id FROM symbols WHERE symbol = :symbol)", shares=shares, id=session["user_id"], symbol=symbol)
                db.execute("UPDATE users SET cash = cash + :shares * :price WHERE id = :id", shares=compare, price=price["price"], id=session["user_id"])

            print(stock)
            return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
