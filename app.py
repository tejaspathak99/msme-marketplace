from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///msme.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    products = db.relationship('Product', backref='supplier', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    min_order_qty = db.Column(db.Integer, nullable=False)
    image_filename = db.Column(db.String(200))
    supplier_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Role-based decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                flash('Access denied.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Initialize database and create admin
def init_db():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Admin user created: username=admin, password=admin123')

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'supplier':
            return redirect(url_for('supplier_dashboard'))
        else:
            return redirect(url_for('buyer_dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        
        if not username or not password or not role:
            flash('All fields are required.', 'danger')
            return redirect(url_for('register'))
        
        if role not in ['supplier', 'buyer']:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('register'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

# Admin Dashboard
@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    users = User.query.all()
    products = Product.query.all()
    total_users = len(users)
    total_products = len(products)
    total_suppliers = User.query.filter_by(role='supplier').count()
    total_buyers = User.query.filter_by(role='buyer').count()
    
    return render_template('admin_dashboard.html', 
                         users=users, 
                         products=products,
                         total_users=total_users,
                         total_products=total_products,
                         total_suppliers=total_suppliers,
                         total_buyers=total_buyers)

@app.route('/admin/product/delete/<int:id>')
@login_required
@role_required('admin')
def admin_delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

# Supplier Dashboard
@app.route('/supplier/dashboard')
@login_required
@role_required('supplier')
def supplier_dashboard():
    products = Product.query.filter_by(supplier_id=current_user.id).all()
    return render_template('supplier_dashboard.html', products=products)

@app.route('/supplier/product/add', methods=['GET', 'POST'])
@login_required
@role_required('supplier')
def add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        category = request.form.get('category')
        min_order_qty = request.form.get('min_order_qty')
        image_filename = request.form.get('image_filename')
        
        if not all([name, description, price, category, min_order_qty]):
            flash('All fields except image are required.', 'danger')
            return redirect(url_for('add_product'))
        
        try:
            product = Product(
                name=name,
                description=description,
                price=float(price),
                category=category,
                min_order_qty=int(min_order_qty),
                image_filename=image_filename,
                supplier_id=current_user.id
            )
            db.session.add(product)
            db.session.commit()
            flash('Product added successfully!', 'success')
            return redirect(url_for('supplier_dashboard'))
        except ValueError:
            flash('Invalid price or quantity value.', 'danger')
            return redirect(url_for('add_product'))
    
    return render_template('product_form.html', product=None, action='Add')

@app.route('/supplier/product/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('supplier')
def edit_product(id):
    product = Product.query.get_or_404(id)
    
    if product.supplier_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('supplier_dashboard'))
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.category = request.form.get('category')
        product.min_order_qty = int(request.form.get('min_order_qty'))
        product.image_filename = request.form.get('image_filename')
        
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('supplier_dashboard'))
    
    return render_template('product_form.html', product=product, action='Edit')

@app.route('/supplier/product/delete/<int:id>')
@login_required
@role_required('supplier')
def delete_product(id):
    product = Product.query.get_or_404(id)
    
    if product.supplier_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('supplier_dashboard'))
    
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully.', 'success')
    return redirect(url_for('supplier_dashboard'))

# Buyer Dashboard
@app.route('/buyer/dashboard')
@login_required
@role_required('buyer')
def buyer_dashboard():
    products = Product.query.all()
    return render_template('buyer_dashboard.html', products=products)

@app.route('/product/<int:id>')
@login_required
def view_product(id):
    product = Product.query.get_or_404(id)
    return render_template('product_view.html', product=product)

# Search
@app.route('/search')
@login_required
def search():
    keyword = request.args.get('keyword', '')
    category = request.args.get('category', '')
    sort_by = request.args.get('sort', '')
    
    query = Product.query
    
    if keyword:
        query = query.filter(
            (Product.name.contains(keyword)) | 
            (Product.description.contains(keyword))
        )
    
    if category:
        query = query.filter_by(category=category)
    
    if sort_by == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_high':
        query = query.order_by(Product.price.desc())
    
    products = query.all()
    categories = db.session.query(Product.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('search.html', 
                         products=products, 
                         categories=categories,
                         keyword=keyword,
                         selected_category=category,
                         sort_by=sort_by)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))