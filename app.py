from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for, flash
import mysql.connector

app = Flask(__name__)
app.secret_key = 'your_secret_key'

def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='root123',
        database='project'
    )

@app.route('/')
def home():
    if 'username' in session:
        return render_template('home.html')
    else:
        flash("Check username")
        return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        con = get_db_connection()
        cursor = con.cursor()
        try:
            cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", (username, email, password))
            con.commit()
            flash("Registered successfully! You can now log in.")
        except mysql.connector.IntegrityError:
            flash("Email already registered.")
        cursor.close()
        con.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    con = get_db_connection()
    cursor = con.cursor(dictionary=True)
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        cursor.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        con.close()

        if user:
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['email'] = user['email']
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return render_template('logout.html')

@app.route('/products', methods=['GET', 'POST'])
def products():
    con = get_db_connection()
    cursor = con.cursor(dictionary=True)
    if request.method == 'POST':
        quantity = request.form.get('quantity')
        user_id = session.get('user_id')
        product_id = request.form.get('product_id')
        if quantity and product_id and user_id:
            try:
                call_cursor = con.cursor()
                call_cursor.callproc('AddToCart', [user_id, product_id, int(quantity)])
                con.commit()
                call_cursor.close()
            except Exception as e:
                print("Error calling AddToCart:", e)
                con.rollback()

    cursor.execute("""
        SELECT p.*, c.name AS category 
        FROM products p
        JOIN category c ON p.category_id = c.category_id
    """)
    prod = cursor.fetchall()
    cursor.close()
    con.close()
    return render_template('products.html', prod=prod)

@app.route('/cart', methods=['GET', 'POST'])
def displaycart():
    if 'username' not in session:
        flash("Please login to view your cart.")
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    con = get_db_connection()
    cursor = con.cursor(dictionary=True)

    if request.method == 'POST':
        product_id = request.form.get('product_id')
        quantity = request.form.get('quantity')
        action = request.form.get('action')
        try:
            product_id = int(product_id)
            if action == 'remove':
                cursor.execute('DELETE FROM cart WHERE product_id = %s AND user_id = %s', (product_id, user_id))
            elif action == 'update':
                quantity = int(quantity)
                cursor.execute('UPDATE cart SET quantity = %s WHERE product_id = %s AND user_id = %s',
                               (quantity, product_id, user_id))
            con.commit()
        except Exception as e:
            print("Error processing cart action:", e)
            con.rollback()

    cursor.execute('''
        SELECT p.product_id, p.name, p.price, p.image_path, p.description, c.quantity
        FROM cart c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = %s
    ''', (user_id,))
    cart_items = cursor.fetchall()
    cart_total = sum(item['price'] * item['quantity'] for item in cart_items)
    session['cart_total'] = cart_total
    empty = not cart_items

    cursor.close()
    con.close()

    return render_template('cart.html', cart_total=cart_total, cart_items=cart_items, empty=empty)

@app.route('/order', methods=['GET', 'POST'])
def order():
    user_id = session.get('user_id')
    if not user_id:
        return redirect('/login')

    con = get_db_connection()
    cursor = con.cursor()

    cursor.execute('''
        SELECT p.product_id, p.name, p.price, p.image_path, p.description, c.quantity
        FROM cart c
        JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = %s
    ''', (user_id,))
    cart_items = cursor.fetchall()

    if request.method == 'POST':
        address = request.form.get('shipping_address')
        phone = request.form.get('phone_number')
        total_amount = session.get('cart_total', 0)
        status = request.form.get('status')
        order_date = datetime.today().date()
        try:
            cursor.execute("""
                INSERT INTO Orders (user_id, order_date, total_amount, status, shipping_address, shipping_phone_number)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, order_date, total_amount, status, address, phone))
            con.commit()

            cursor.execute("SELECT LAST_INSERT_ID()")
            order_id = cursor.fetchone()[0]

            for item in cart_items:
                product_id = item[0]
                quantity = item[5]
                unit_price = item[2]
                cursor.execute("""
                    INSERT INTO Order_Items (order_id, product_id, quantity, unit_price)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, product_id, quantity, unit_price))
            con.commit()

            cursor.execute('DELETE FROM cart WHERE user_id = %s', (user_id,))
            con.commit()

            return render_template('order-confirm.html', order_id=order_id, total_amount=total_amount)
        except Exception as e:
            con.rollback()
            return f"Error placing order: {str(e)}"
        finally:
            cursor.close()
            con.close()

    return render_template('order.html', cart_items=cart_items, total_amount=session.get('cart_total', 0))

# Admin/owner view
@app.route('/orders')
def admin_orders():
    if 'username' in session and session['username'] == 'admin':  # Replace 'admin' with actual owner username
        con = get_db_connection()
        cursor = con.cursor(dictionary=True)
        cursor.execute('''
            SELECT o.order_id, u.username, o.order_date, o.total_amount, o.status, o.shipping_address, o.shipping_phone_number
            FROM Orders o
            JOIN users u ON o.user_id = u.user_id
            ORDER BY o.order_date DESC
        ''')
        orders = cursor.fetchall()
        cursor.close()
        con.close()
        return render_template('admin-orders.html', orders=orders)
    else:
        flash("Unauthorized access.")
        return redirect(url_for('home'))
    
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    con = get_db_connection()
    cursor = con.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']
        category_id = request.form['category_id']
        image_path = request.form['image_path']

        try:
            cursor.execute("""
                INSERT INTO products (name, description, price, category_id, image_path)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, description, price, category_id, image_path))
            con.commit()
            flash('Product added successfully!')
            return redirect(url_for('products'))
        except Exception as e:
            con.rollback()
            flash(f'Error: {e}')

    cursor.execute("SELECT category_id, name FROM category")
    categories = cursor.fetchall()
    cursor.close()
    con.close()
    return render_template('add-product.html', categories=categories)

if __name__ == '__main__':
    app.run(debug=True, port=8000)
