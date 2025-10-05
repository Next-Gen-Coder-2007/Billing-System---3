from flask import Flask, render_template, redirect, url_for, request, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pdfkit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://billing_system_3_user:f258FiKPqjJpLNltTvvEcD0lwYcReSNi@dpg-d3h0i8p5pdvs73es2aj0-a.oregon-postgres.render.com/billing_system_3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Customer(db.Model):
    __tablename__ = 'customer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    gstin = db.Column(db.String(150), unique=True, nullable=True)
    address_line1 = db.Column(db.String(200), nullable=False)
    address_line2 = db.Column(db.String(200), nullable=True)

    # Bills
    gst_bills = db.relationship('GSTBill', backref='customer', lazy=True)
    non_gst_bills = db.relationship('NonGSTBill', backref='customer', lazy=True)
    job_bills = db.relationship('JobBill', backref='customer', lazy=True)

    # Ledger
    money_ledger = db.relationship('MoneyLedger', backref='customer', uselist=False)


class GSTBill(db.Model):
    __tablename__ = 'gst_bill'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float)
    gst_amount = db.Column(db.Float)
    items = db.relationship('GSTBillItem', backref='bill', lazy=True)


class NonGSTBill(db.Model):
    __tablename__ = 'non_gst_bill'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float)
    items = db.relationship('NonGSTBillItem', backref='bill', lazy=True)


class JobBill(db.Model):
    __tablename__ = 'job_bill'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float)
    description = db.Column(db.String(500))
    items = db.relationship('JobBillItem', backref='bill', lazy=True)


class GSTBillItem(db.Model):
    __tablename__ = 'gst_bill_item'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('gst_bill.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)


class NonGSTBillItem(db.Model):
    __tablename__ = 'non_gst_bill_item'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('non_gst_bill.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)


class JobBillItem(db.Model):
    __tablename__ = 'job_bill_item'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('job_bill.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)

class MoneyLedger(db.Model):
    __tablename__ = 'money_ledger'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    
    # Relationship to transactions
    transactions = db.relationship('MoneyTransaction', backref='ledger', lazy=True, order_by="MoneyTransaction.date")
    
    def __repr__(self):
        return f"<MoneyLedger customer_id={self.customer_id}>"

class MoneyTransaction(db.Model):
    __tablename__ = 'money_transaction'
    id = db.Column(db.Integer, primary_key=True)
    ledger_id = db.Column(db.Integer, db.ForeignKey('money_ledger.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # Positive for credit, negative for debit
    date = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(200))

    def __repr__(self):
        txn_type = "Credit" if self.amount > 0 else "Debit"
        return f"<MoneyTransaction {txn_type} {self.amount}>"


@app.route('/')
def dashboard():
    # Initialize aggregates
    gst_total = gst_received = gst_pending = 0.0
    non_gst_total = non_gst_received = non_gst_pending = 0.0
    job_total = job_received = job_pending = 0.0

    # Fetch all customers
    customers = Customer.query.all()

    for customer in customers:
        # --- GST Bills ---
        gst_bills = GSTBill.query.filter_by(customer_id=customer.id).all()
        gst_total += sum(bill.total for bill in gst_bills)

        # Calculate received amount for GST bills
        gst_received += sum(
            min(bill.total, sum(txn.amount for txn in customer.money_ledger.transactions if txn.amount > 0))
            for bill in gst_bills
        )
        gst_pending = gst_total - gst_received

        # --- Non-GST Bills ---
        non_gst_bills = NonGSTBill.query.filter_by(customer_id=customer.id).all()
        non_gst_total += sum(bill.total for bill in non_gst_bills)

        # Calculate received amount for Non-GST bills
        non_gst_received += sum(
            min(bill.total, sum(txn.amount for txn in customer.money_ledger.transactions if txn.amount > 0))
            for bill in non_gst_bills
        )
        non_gst_pending = non_gst_total - non_gst_received

        # --- Job Bills ---
        job_bills = JobBill.query.filter_by(customer_id=customer.id).all()
        job_total += sum(bill.total for bill in job_bills)

        # Calculate received amount for Job bills
        job_received += sum(
            min(bill.total, sum(txn.amount for txn in customer.money_ledger.transactions if txn.amount > 0))
            for bill in job_bills
        )
        job_pending = job_total - job_received

    return render_template(
        'home.html',
        gst_total=gst_total,
        gst_received=gst_received,
        gst_pending=gst_pending,
        non_gst_total=non_gst_total,
        non_gst_received=non_gst_received,
        non_gst_pending=non_gst_pending,
        job_total=job_total,
        job_received=job_received,
        job_pending=job_pending,
    )
# ----------------------------
# Ledger Routes
# ----------------------------
@app.route('/ledger/<int:customer_id>')
def view_ledger(customer_id):
    ledger = MoneyLedger.query.filter_by(customer_id=customer_id).first()
    return render_template('ledger.html', ledger=ledger)

@app.route('/customers')
def customer_list():
    customers = Customer.query.all()
    return render_template('customer_list.html', customers=customers)


# ----------------------------
# Add Customer
# ----------------------------
@app.route('/customer/add', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        gstin = request.form.get('gstin')
        address1 = request.form['address_line1']
        address2 = request.form.get('address_line2')
        customer = Customer(
            name=name,
            phone=phone,
            gstin=gstin,
            address_line1=address1,
            address_line2=address2
        )
        db.session.add(customer)
        db.session.commit()
        ledger = MoneyLedger(customer_id=customer.id)
        db.session.add(ledger)
        db.session.commit()

        flash('Customer added successfully!', 'success')
        return redirect(url_for('customer_list'))

    return render_template('customer_add.html')


# ----------------------------
# Edit Customer
# ----------------------------
@app.route('/customer/edit/<int:id>', methods=['GET', 'POST'])
def edit_customer(id):
    customer = Customer.query.get_or_404(id)
    if request.method == 'POST':
        customer.name = request.form['name']
        customer.phone = request.form['phone']
        customer.gstin = request.form.get('gstin')
        customer.address_line1 = request.form['address_line1']
        customer.address_line2 = request.form.get('address_line2')

        db.session.commit()
        flash('Customer updated successfully!', 'success')
        return redirect(url_for('customer_list'))

    return render_template('customer_edit.html', customer=customer)


# ----------------------------
# Delete Customer
# ----------------------------
@app.route('/customer/delete/<int:id>', methods=['POST'])
def delete_customer(id):
    customer = Customer.query.get_or_404(id)

    # Delete ledger first
    if customer.money_ledger:
        db.session.delete(customer.money_ledger)

    db.session.delete(customer)
    db.session.commit()
    flash('Customer deleted successfully!', 'success')
    return redirect(url_for('customer_list'))


# ----------------------------
# View Customer Details (Bills + Ledger)
# ----------------------------
@app.route('/customer/<int:id>')
def customer_detail(id):
    customer = Customer.query.get_or_404(id)

    gst_bills = customer.gst_bills
    non_gst_bills = customer.non_gst_bills
    job_bills = customer.job_bills
    ledger = customer.money_ledger

    return render_template('customer_detail.html',
                           customer=customer,
                           gst_bills=gst_bills,
                           non_gst_bills=non_gst_bills,
                           job_bills=job_bills,
                           ledger=ledger)

@app.route('/gst_bills')
def gst_bill_list():
    bills = GSTBill.query.all()
    return render_template('gst_bill_list.html', bills=bills)


# ----------------------------
# Add GST Bill
# ----------------------------
@app.route('/gst_bill/add', methods=['GET', 'POST'])
def add_gst_bill():
    customers = Customer.query.all()

    if request.method == 'POST':
        customer_id = int(request.form['customer_id'])
        customer = Customer.query.get_or_404(customer_id)

        # Create the GST bill
        gst_bill = GSTBill(
            customer_id=customer_id,
            gst_amount=0.0,
            total=0.0
        )
        db.session.add(gst_bill)
        db.session.commit()  # Commit to get bill.id

        total = 0
        gst_total = 0

        # Add bill items
        items = request.form.getlist('item_name[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        for name, qty, price in zip(items, quantities, prices):
            qty = int(qty)
            price = float(price)
            item_total = qty * price
            gst_amount = item_total * 0.18  # Assuming 18% GST

            gst_total += gst_amount
            total += item_total + gst_amount

            bill_item = GSTBillItem(
                bill_id=gst_bill.id,
                name=name,
                quantity=qty,
                price=price
            )
            db.session.add(bill_item)

        gst_bill.total = total
        gst_bill.gst_amount = gst_total
        db.session.commit()

        # Automatic ledger debit
        customer = Customer.query.get(customer_id)
        ledger = customer.money_ledger
        if ledger:
            txn = MoneyTransaction(
                ledger_id=ledger.id,
                amount=-total,  # negative for debit
                note=f'Debit for GST Bill #{gst_bill.id}'
            )
            db.session.add(txn)
            db.session.commit()

        flash(f'GST Bill #{gst_bill.id} created successfully!', 'success')
        return redirect(url_for('gst_bill_list'))

    return render_template('gst_bill_add.html', customers=customers)


# ----------------------------
# View GST Bill Details
# ----------------------------
@app.route('/gst_bill/<int:id>')
def gst_bill_detail(id):
    bill = GSTBill.query.get_or_404(id)
    items = bill.items
    customer = bill.customer
    return render_template('gst_bill_detail.html', bill=bill, items=items, customer=customer)

# Delete GST Bill
@app.route('/gst_bill/delete/<int:id>', methods=['POST'])
def delete_gst_bill(id):
    bill = GSTBill.query.get_or_404(id)
    customer = bill.customer

    # Delete all bill items
    for item in bill.items:
        db.session.delete(item)

    ledger = customer.money_ledger
    if ledger:
        txn = MoneyTransaction.query.filter_by(
            ledger_id=ledger.id,
            note=f'Debit for GST Bill #{bill.id}'
        ).first()
        if txn:
            db.session.delete(txn)
            db.session.commit()

    # Delete the bill
    db.session.delete(bill)
    db.session.commit()

    flash(f'GST Bill #{id} deleted successfully!', 'success')
    return redirect(url_for('gst_bill_list'))

# Edit GST Bill
@app.route('/gst_bill/edit/<int:id>', methods=['GET', 'POST'])
def edit_gst_bill(id):
    bill = GSTBill.query.get_or_404(id)
    customer = bill.customer

    if request.method == 'POST':

        # Delete old items
        for item in bill.items:
            db.session.delete(item)

        # Add updated items
        items = request.form.getlist('item_name[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        total = 0
        gst_total = 0

        for name, qty, price in zip(items, quantities, prices):
            qty = int(qty)
            price = float(price)
            item_total = qty * price
            gst_amount = item_total * 0.18  # 18% GST
            gst_total += gst_amount
            total += item_total + gst_amount

            bill_item = GSTBillItem(
                bill_id=bill.id,
                name=name,
                quantity=qty,
                price=price
            )
            db.session.add(bill_item)

        bill.total = total
        bill.gst_amount = gst_total
        db.session.commit()

        # Update ledger transaction
        ledger = customer.money_ledger
        txn = MoneyTransaction.query.filter_by(
            ledger_id=ledger.id,
            note=f'Debit for GST Bill #{bill.id}'
        ).first()

        if txn:
            # Update debit amount to match new bill total
            txn.amount = -bill.total
            db.session.commit()

        flash(f'GST Bill #{id} updated successfully!', 'success')
        return redirect(url_for('gst_bill_list'))

    return render_template('gst_bill_edit.html', bill=bill, customer=customer)

@app.route('/non_gst_bills')
def non_gst_bill_list():
    bills = NonGSTBill.query.all()
    return render_template('non_gst_bill_list.html', bills=bills)


# ----------------------------
# Add Non-GST Bill
# ----------------------------
@app.route('/non_gst_bill/add', methods=['GET', 'POST'])
def add_non_gst_bill():
    customers = Customer.query.all()

    if request.method == 'POST':
        customer_id = int(request.form['customer_id'])
        customer = Customer.query.get_or_404(customer_id)

        bill = NonGSTBill(customer_id=customer_id, total=0.0)
        db.session.add(bill)
        db.session.commit()  # To get bill.id

        total = 0
        items = request.form.getlist('item_name[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        for name, qty, price in zip(items, quantities, prices):
            qty = int(qty)
            price = float(price)
            item_total = qty * price
            total += item_total

            bill_item = NonGSTBillItem(
                bill_id=bill.id,
                name=name,
                quantity=qty,
                price=price
            )
            db.session.add(bill_item)

        bill.total = total
        db.session.commit()


        # Automatic ledger debit
        customer = Customer.query.get(customer_id)
        ledger = customer.money_ledger
        if ledger:
            txn = MoneyTransaction(
                ledger_id=ledger.id,
                amount=-total,
                note=f'Debit for Non-GST Bill #{bill.id}'
            )
            db.session.add(txn)
            db.session.commit()

        flash(f'Non-GST Bill #{bill.id} created successfully!', 'success')
        return redirect(url_for('non_gst_bill_list'))

    return render_template('non_gst_bill_add.html', customers=customers)


# ----------------------------
# View Non-GST Bill Details
# ----------------------------
@app.route('/non_gst_bill/<int:id>')
def non_gst_bill_detail(id):
    bill = NonGSTBill.query.get_or_404(id)
    items = bill.items
    customer = bill.customer
    return render_template('non_gst_bill_detail.html', bill=bill, items=items, customer=customer)


# ----------------------------
# Delete Non-GST Bill
# ----------------------------
@app.route('/non_gst_bill/delete/<int:id>', methods=['POST'])
def delete_non_gst_bill(id):
    bill = NonGSTBill.query.get_or_404(id)
    customer = bill.customer

    for item in bill.items:
        db.session.delete(item)

    ledger = customer.money_ledger
    if ledger:
        txn = MoneyTransaction.filter_by(
            ledger_id=ledger.id,
            note=f'Debit for Non-GST Bill #{bill.id}'
        )
        db.session.delete(txn)
        db.session.commit()

    db.session.delete(bill)
    db.session.commit()
    flash(f'Non-GST Bill #{id} deleted successfully!', 'success')
    return redirect(url_for('non_gst_bill_list'))


# ----------------------------
# Edit Non-GST Bill
# ----------------------------
@app.route('/non_gst_bill/edit/<int:id>', methods=['GET', 'POST'])
def edit_non_gst_bill(id):
    bill = NonGSTBill.query.get_or_404(id)
    customer = bill.customer

    if request.method == 'POST':
        # Delete old items
        for item in bill.items:
            db.session.delete(item)

        # Add updated items
        items = request.form.getlist('item_name[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        total = 0
        for name, qty, price in zip(items, quantities, prices):
            qty = int(qty)
            price = float(price)
            item_total = qty * price
            total += item_total

            bill_item = NonGSTBillItem(
                bill_id=bill.id,
                name=name,
                quantity=qty,
                price=price
            )
            db.session.add(bill_item)

        bill.total = total
        db.session.commit()

        # Update ledger transaction
        ledger = customer.money_ledger
        txn = MoneyTransaction.query.filter_by(
            ledger_id=ledger.id,
            note=f'Debit for Non-GST Bill #{bill.id}'
        ).first()

        if txn:
            # Update debit amount to match new bill total
            txn.amount = -bill.total
            db.session.commit()

        flash(f'Non-GST Bill #{id} updated successfully!', 'success')
        return redirect(url_for('non_gst_bill_list'))

    return render_template('non_gst_bill_edit.html', bill=bill, customer=customer)

@app.route('/job_bills')
def job_bill_list():
    bills = JobBill.query.all()
    return render_template('job_bill_list.html', bills=bills)


# ----------------------------
# Add Job Bill
# ----------------------------
@app.route('/job_bill/add', methods=['GET', 'POST'])
def add_job_bill():
    customers = Customer.query.all()

    if request.method == 'POST':
        customer_id = int(request.form['customer_id'])
        customer = Customer.query.get_or_404(customer_id)
        description = request.form.get('description', '')

        bill = JobBill(customer_id=customer_id, total=0.0, description=description)
        db.session.add(bill)
        db.session.commit()  # To get bill.id

        total = 0
        items = request.form.getlist('item_name[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        for name, qty, price in zip(items, quantities, prices):
            qty = int(qty)
            price = float(price)
            item_total = qty * price
            total += item_total

            bill_item = JobBillItem(
                bill_id=bill.id,
                name=name,
                quantity=qty,
                price=price
            )
            db.session.add(bill_item)

        bill.total = total
        db.session.commit()

        customer = Customer.query.get(customer_id)
        ledger = customer.money_ledger
        if ledger:
            txn = MoneyTransaction(
                ledger_id=ledger.id,
                amount=-total,
                note=f'Debit for Job Bill #{bill.id}'
            )
            db.session.add(txn)
            db.session.commit()

        flash(f'Job Bill #{bill.id} created successfully!', 'success')
        return redirect(url_for('job_bill_list'))

    return render_template('job_bill_add.html', customers=customers)


# ----------------------------
# View Job Bill Details
# ----------------------------
@app.route('/job_bill/<int:id>')
def job_bill_detail(id):
    bill = JobBill.query.get_or_404(id)
    items = bill.items
    customer = bill.customer
    return render_template('job_bill_detail.html', bill=bill, items=items, customer=customer)


# ----------------------------
# Delete Job Bill
# ----------------------------
@app.route('/job_bill/delete/<int:id>', methods=['POST'])
def delete_job_bill(id):
    bill = JobBill.query.get_or_404(id)
    customer = bill.customer


    for item in bill.items:
        db.session.delete(item)

    ledger = customer.money_ledger
    if ledger:
        txn = MoneyTransaction.filter_by(
            ledger_id=ledger.id,
            note=f'Debit for Job Bill #{bill.id}'
        )
        db.session.delete(txn)
        db.session.commit()

    db.session.delete(bill)
    db.session.commit()
    flash(f'Job Bill #{id} deleted successfully!', 'success')
    return redirect(url_for('job_bill_list'))


# ----------------------------
# Edit Job Bill
# ----------------------------
@app.route('/job_bill/edit/<int:id>', methods=['GET', 'POST'])
def edit_job_bill(id):
    bill = JobBill.query.get_or_404(id)
    customer = bill.customer

    if request.method == 'POST':

        # Update description
        bill.description = request.form.get('description', '')

        # Delete old items
        for item in bill.items:
            db.session.delete(item)

        # Add updated items
        items = request.form.getlist('item_name[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        total = 0
        for name, qty, price in zip(items, quantities, prices):
            qty = int(qty)
            price = float(price)
            item_total = qty * price
            total += item_total

            bill_item = JobBillItem(
                bill_id=bill.id,
                name=name,
                quantity=qty,
                price=price
            )
            db.session.add(bill_item)

        bill.total = total
        db.session.commit()

        # Update ledger transaction
        ledger = customer.money_ledger
        txn = MoneyTransaction.query.filter_by(
            ledger_id=ledger.id,
            note=f'Debit for Job Bill #{bill.id}'
        ).first()

        if txn:
            # Update debit amount to match new bill total
            txn.amount = -bill.total
            db.session.commit()

        flash(f'Job Bill #{id} updated successfully!', 'success')
        return redirect(url_for('job_bill_list'))

    return render_template('job_bill_edit.html', bill=bill, customer=customer)


@app.route('/customer/<int:customer_id>/gst_bills')
def customer_gst_bills(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    bills = GSTBill.query.filter_by(customer_id=customer_id).all()
    return render_template('customer_gst_bills.html', customer=customer, bills=bills)

@app.route('/customer/<int:customer_id>/non_gst_bills')
def customer_non_gst_bills(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    bills = NonGSTBill.query.filter_by(customer_id=customer_id).all()
    return render_template('customer_non_gst_bills.html', customer=customer, bills=bills)

@app.route('/customer/<int:customer_id>/job_bills')
def customer_job_bills(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    bills = JobBill.query.filter_by(customer_id=customer_id).all()
    return render_template('customer_job_bills.html', customer=customer, bills=bills)

@app.route('/customer/<int:customer_id>/money_ledger', methods=['GET', 'POST'])
def money_ledger_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    ledger = customer.money_ledger

    if request.method == 'POST':
        # Add new transaction
        amount = float(request.form['amount'])
        txn_type = request.form['type']
        note = request.form.get('note', '')

        if txn_type == 'debit':
            amount = -abs(amount)
        else:
            amount = abs(amount)

        txn = MoneyTransaction(ledger_id=ledger.id, amount=amount, note=note)
        db.session.add(txn)
        db.session.commit()
        flash('Transaction added successfully!', 'success')
        return redirect(url_for('money_ledger_detail', customer_id=customer_id))

    transactions = ledger.transactions if ledger else []
    balance = sum(txn.amount for txn in transactions)

    return render_template('money_ledger.html', customer=customer, transactions=transactions, balance=balance)

@app.route('/customer/<int:customer_id>/money_ledger/edit/<int:txn_id>', methods=['GET', 'POST'])
def edit_transaction(customer_id, txn_id):
    customer = Customer.query.get_or_404(customer_id)
    txn = MoneyTransaction.query.get_or_404(txn_id)

    if request.method == 'POST':
        amount = float(request.form['amount'])
        txn_type = request.form['type']
        txn.note = request.form.get('note', '')

        if txn_type == 'debit':
            txn.amount = -abs(amount)
        else:
            txn.amount = abs(amount)

        db.session.commit()
        flash('Transaction updated successfully!', 'success')
        return redirect(url_for('money_ledger_detail', customer_id=customer_id))

    return render_template('edit_transaction.html', customer=customer, txn=txn)

@app.route('/customer/<int:customer_id>/money_ledger/delete/<int:txn_id>', methods=['POST'])
def delete_transaction(customer_id, txn_id):
    customer = Customer.query.get_or_404(customer_id)
    txn = MoneyTransaction.query.get_or_404(txn_id)

    db.session.delete(txn)
    db.session.commit()
    flash('Transaction deleted successfully!', 'success')
    return redirect(url_for('money_ledger_detail', customer_id=customer_id))



@app.route('/bill/<int:bill_id>/pdf')
def download_gst_bill(bill_id):
    bill = GSTBill.query.get_or_404(bill_id)
    customer = bill.customer
    rendered = render_template("bill_pdf.html", bill=bill, customer=customer)

    pdf = pdfkit.from_string(rendered, False)  # False → returns PDF as bytes

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=bill_{bill.id}.pdf'
    return response

@app.route('/bill_non/<int:bill_id>/pdf')
def download_non_gst_bill(bill_id):
    bill = NonGSTBILL.query.get_or_404(bill_id)
    customer = bill.customer
    rendered = render_template("bill_pdf.html", bill=bill, customer=customer)

    pdf = pdfkit.from_string(rendered, False)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=bill_{bill.id}.pdf'
    return response

@app.route('/bill_job/<int:bill_id>/pdf')
def download_job_bill(bill_id):
    bill = JobBill.query.get_or_404(bill_id)
    customer = bill.customer
    rendered = render_template("bill_pdf.html", bill=bill, customer=customer)

    pdf = pdfkit.from_string(rendered, False)

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=bill_{bill.id}.pdf'
    return response

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
