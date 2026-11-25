import os, sqlite3
import json, math
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from werkzeug.security import check_password_hash, generate_password_hash
from urllib.parse import urlencode
from urllib.request import Request, urlopen

app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","change-this-secret-before-deployment")
DB=os.path.join(os.path.dirname(__file__),"common_table.db")
ADMIN_USER=os.environ.get("ADMIN_USERNAME","admin")
ADMIN_HASH=os.environ.get("ADMIN_PASSWORD_HASH",generate_password_hash("ChangeMe123!"))
TYPES=["Food pantry","Free meal","Community support"]

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS resources(
        id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,resource_type TEXT NOT NULL,
        address TEXT NOT NULL,city TEXT NOT NULL,postal_code TEXT DEFAULT '',phone TEXT DEFAULT '',
        website TEXT DEFAULT '',description TEXT DEFAULT '',opening_time TEXT DEFAULT '09:00',
        closing_time TEXT DEFAULT '17:00',open_days TEXT DEFAULT '0,1,2,3,4,5,6',
        verified INTEGER DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        if c.execute("SELECT COUNT(*) FROM resources").fetchone()[0]==0:
            c.executemany("""INSERT INTO resources(name,resource_type,address,city,postal_code,description)
            VALUES(?,?,?,?,?,?)""",[
            ("Demo Community Pantry","Food pantry","214 Example Street","Bengaluru","560001","DEMO LISTING — replace with a verified provider."),
            ("Demo Community Kitchen","Free meal","18 Sample Market Road","Bengaluru","560002","DEMO LISTING — replace with a verified provider.")])

def open_now(r):
    try:
        n=datetime.now()
        return str(n.weekday()) in (r["open_days"] or "").split(",") and r["opening_time"]<=n.strftime("%H:%M")<r["closing_time"]
    except: return False

def admin(fn):
    @wraps(fn)
    def inner(*a,**k):
        if not session.get("admin"): return redirect(url_for("login",next=request.path))
        return fn(*a,**k)
    return inner

@app.get("/")
def home(): return render_template("index.html")

@app.get("/api/resources")
def resources_api():
    q=request.args.get("q",request.args.get("location","")).strip(); typ=request.args.get("type","all"); only=request.args.get("open_now")=="1"
    sql="SELECT * FROM resources WHERE 1=1"; p=[]
    if q:
        like="%"+q+"%"
        sql+=" AND (name LIKE ? OR address LIKE ? OR city LIKE ? OR description LIKE ?)"
        p += [like]*4
    if typ!="all": sql+=" AND resource_type=?"; p.append(typ)
    with db() as c: rows=c.execute(sql+" ORDER BY name",p).fetchall()
    out=[]
    for r in rows:
        x=dict(r); x["open_now"]=open_now(r); x["open_days"]=[int(v) for v in (r["open_days"] or "").split(",") if v.isdigit()]
        if not only or x["open_now"]: out.append(x)
    return jsonify(count=len(out),resources=out)

def valid_coordinate(value, low, high):
    try:
        number=float(value)
        return number if math.isfinite(number) and low <= number <= high else None
    except (TypeError, ValueError):
        return None

def meters_between(lat1, lon1, lat2, lon2):
    radius=6371000
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*radius*math.atan2(math.sqrt(a),math.sqrt(1-a))

@app.get("/api/nearby-food")
def nearby_food_api():
    lat=valid_coordinate(request.args.get("lat"),-90,90)
    lon=valid_coordinate(request.args.get("lon"),-180,180)
    if lat is None or lon is None:
        return jsonify(error="A valid GPS latitude and longitude are required."),400
    # Public OSM data only contains places that contributors have mapped; this is not a complete provider directory.
    query=(f"[out:json][timeout:20];("
           f"nwr(around:500,{lat},{lon})[amenity=social_facility][social_facility~\"^(food_bank|soup_kitchen)$\"];"
           f"nwr(around:500,{lat},{lon})[amenity=food_sharing];"
           f");out center tags;")
    req=Request("https://overpass-api.de/api/interpreter",data=urlencode({"data":query}).encode(),
                headers={"User-Agent":"CommonTableHackathon/1.0 (food-support finder)","Content-Type":"application/x-www-form-urlencoded"})
    try:
        with urlopen(req,timeout=25) as response:
            elements=json.loads(response.read().decode("utf-8")).get("elements",[])
    except Exception:
        return jsonify(error="The live OpenStreetMap search is temporarily unavailable. Try again shortly."),503
    places=[]
    for element in elements:
        tags=element.get("tags",{})
        point=element if "lat" in element else element.get("center",{})
        if "lat" not in point or "lon" not in point:
            continue
        place_lat,place_lon=float(point["lat"]),float(point["lon"])
        distance=meters_between(lat,lon,place_lat,place_lon)
        if distance>500:
            continue
        kind=(tags.get("social_facility") or ("food_sharing" if tags.get("amenity")=="food_sharing" else "food_support"))
        street=" ".join(part for part in [tags.get("addr:housenumber"),tags.get("addr:street")] if part)
        address=", ".join(part for part in [street,tags.get("addr:suburb"),tags.get("addr:city")] if part)
        places.append({"id":f"{element.get('type')}/{element.get('id')}","name":tags.get("name") or tags.get("operator") or "Food support location",
                       "kind":kind.replace("_"," ").title(),"lat":place_lat,"lon":place_lon,"distance_m":round(distance),
                       "address":address,"phone":tags.get("phone",""),"website":tags.get("website",""),
                       "opening_hours":tags.get("opening_hours",""),"source":"OpenStreetMap","verified":False})
    places.sort(key=lambda place:place["distance_m"])
    return jsonify(radius_m=500,count=len(places),places=places,source="OpenStreetMap contributors")

@app.get("/api/route")
def route_api():
    origin_lat=valid_coordinate(request.args.get("from_lat"),-90,90)
    origin_lon=valid_coordinate(request.args.get("from_lon"),-180,180)
    dest_lat=valid_coordinate(request.args.get("to_lat"),-90,90)
    dest_lon=valid_coordinate(request.args.get("to_lon"),-180,180)
    if None in (origin_lat,origin_lon,dest_lat,dest_lon):
        return jsonify(error="Valid origin and destination coordinates are required."),400
    coords=f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    url=f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson&steps=false"
    req=Request(url,headers={"User-Agent":"CommonTableHackathon/1.0 (food-support finder)"})
    try:
        with urlopen(req,timeout=20) as response:
            data=json.loads(response.read().decode("utf-8"))
        route=data["routes"][0]
        return jsonify(geometry=route["geometry"],distance_m=round(route["distance"]),duration_s=round(route["duration"]))
    except Exception:
        return jsonify(error="A road route is temporarily unavailable."),503

@app.route("/admin/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form.get("username")==ADMIN_USER and check_password_hash(ADMIN_HASH,request.form.get("password","")):
            session["admin"]=True; return redirect(url_for("dashboard"))
        flash("Incorrect username or password.","error")
    return render_template("login.html")

@app.get("/admin/logout")
def logout(): session.clear(); return redirect(url_for("home"))

@app.get("/admin")
@admin
def dashboard():
    with db() as c: rows=c.execute("SELECT * FROM resources ORDER BY id DESC").fetchall()
    return render_template("admin.html",rows=rows)

def form_data(f):
    d={k:f.get(k,"").strip() for k in ["name","resource_type","address","city","postal_code","phone","website","description","opening_time","closing_time"]}
    d["open_days"]=",".join(str(i) for i in range(7) if str(i) in f.getlist("open_days"))
    d["verified"]=1 if f.get("verified") else 0
    if not d["name"] or not d["address"] or not d["city"]: raise ValueError("Name, address and city are required.")
    if d["resource_type"] not in TYPES: raise ValueError("Choose a valid resource type.")
    if not d["open_days"]: raise ValueError("Choose at least one open day.")
    try:
        datetime.strptime(d["opening_time"],"%H:%M"); datetime.strptime(d["closing_time"],"%H:%M")
    except: raise ValueError("Enter valid opening and closing times.")
    if d["opening_time"]>=d["closing_time"]: raise ValueError("Closing time must be later than opening time.")
    if d["website"] and not d["website"].startswith(("http://","https://")): d["website"]="https://"+d["website"]
    return d

@app.route("/admin/resources/new",methods=["GET","POST"])
@admin
def add():
    if request.method=="POST":
        try:
            d=form_data(request.form)
            with db() as c: c.execute("""INSERT INTO resources(name,resource_type,address,city,postal_code,phone,website,description,opening_time,closing_time,open_days,verified)
            VALUES(:name,:resource_type,:address,:city,:postal_code,:phone,:website,:description,:opening_time,:closing_time,:open_days,:verified)""",d)
            flash("Resource added.","success"); return redirect(url_for("dashboard"))
        except ValueError as e: flash(str(e),"error")
    return render_template("resource_form.html",r=None,title="Add resource",types=TYPES)

@app.route("/admin/resources/<int:rid>/edit",methods=["GET","POST"])
@admin
def edit(rid):
    with db() as c: r=c.execute("SELECT * FROM resources WHERE id=?",(rid,)).fetchone()
    if not r: abort(404)
    if request.method=="POST":
        try:
            d=form_data(request.form); d["id"]=rid
            with db() as c: c.execute("""UPDATE resources SET name=:name,resource_type=:resource_type,address=:address,city=:city,postal_code=:postal_code,phone=:phone,website=:website,description=:description,opening_time=:opening_time,closing_time=:closing_time,open_days=:open_days,verified=:verified WHERE id=:id""",d)
            flash("Resource updated.","success"); return redirect(url_for("dashboard"))
        except ValueError as e: flash(str(e),"error")
    return render_template("resource_form.html",r=r,title="Edit resource",types=TYPES)

@app.post("/admin/resources/<int:rid>/delete")
@admin
def delete(rid):
    with db() as c: c.execute("DELETE FROM resources WHERE id=?",(rid,))
    flash("Resource deleted.","success"); return redirect(url_for("dashboard"))

@app.get("/health")
def health(): return jsonify(status="ok",application="Common Table")

init_db()
if __name__=="__main__": app.run(debug=True)
