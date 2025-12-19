"""
Game Day Traders - Main Flask Application
A web application for trading stocks in players alongside board games.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gametraders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Add custom Jinja filter for JSON parsing
@app.template_filter('from_json')
def from_json_filter(s):
    if s:
        return json.loads(s)
    return {}

# ============== Database Models ==============

class Game(db.Model):
    """Represents a trading game session"""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, ended
    winner_id = db.Column(db.String(36), nullable=True)
    num_players = db.Column(db.Integer, nullable=False)
    num_viewers = db.Column(db.Integer, nullable=False)
    player_names = db.Column(db.Text, nullable=False)  # Comma-separated player names (tradeable entities)
    admin_token = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # Scoring system
    scoring_mode = db.Column(db.String(20), default='outright_winner')  # outright_winner, final_points, top_positions
    include_cash = db.Column(db.Boolean, default=False)  # Whether to include cash in final scoring
    position_values = db.Column(db.Text, nullable=True)  # JSON string: {"1": 10, "2": 5, "3": 0}
    final_scores = db.Column(db.Text, nullable=True)  # JSON string of final player scores when game ends
    
    participants = db.relationship('Participant', backref='game', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='game', lazy=True, cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='game', lazy=True, cascade='all, delete-orphan')


class Participant(db.Model):
    """Represents a player or viewer in a game"""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = db.Column(db.String(36), db.ForeignKey('game.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'player', 'viewer', or 'admin'
    access_token = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    cash = db.Column(db.Float, default=0.0)
    
    holdings = db.relationship('Holding', backref='participant', lazy=True, cascade='all, delete-orphan')


class Holding(db.Model):
    """Represents shares held by a participant"""
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.String(36), db.ForeignKey('participant.id'), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)  # The player being traded
    shares = db.Column(db.Integer, default=0)


class Order(db.Model):
    """Represents a buy or sell order"""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.String(36), db.ForeignKey('game.id'), nullable=False)
    participant_id = db.Column(db.String(36), db.ForeignKey('participant.id'), nullable=False)
    order_type = db.Column(db.String(10), nullable=False)  # 'buy' or 'sell'
    player_name = db.Column(db.String(100), nullable=False)  # The player being traded
    price = db.Column(db.Float, nullable=False)
    shares = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='open')  # open, filled, cancelled
    
    participant = db.relationship('Participant', backref='orders')


class Transaction(db.Model):
    """Records completed trades"""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.String(36), db.ForeignKey('game.id'), nullable=False)
    buyer_id = db.Column(db.String(36), nullable=False)
    seller_id = db.Column(db.String(36), nullable=False)
    player_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    shares = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# ============== Routes ==============

@app.route('/')
def index():
    """Home page with option to create a new game"""
    return render_template('index.html')


@app.route('/create-game', methods=['GET', 'POST'])
def create_game():
    """Game creation page and form handler"""
    if request.method == 'POST':
        data = request.form
        
        # Validate player names count
        num_players = int(data.get('num_players', 2))
        player_names = data.get('player_names', '')
        player_names_list = [p.strip() for p in player_names.split(',') if p.strip()]
        
        if len(player_names_list) < num_players:
            error = f"You need at least {num_players} player names in the comma-separated list. You only provided {len(player_names_list)}."
            return render_template('create_game.html', error=error)
        
        # Generate game ID explicitly
        game_id = str(uuid.uuid4())
        
        # Handle scoring mode and position values
        scoring_mode = data.get('scoring_mode', 'outright_winner')
        include_cash = data.get('include_cash') == 'true'
        position_values = None
        
        if scoring_mode == 'top_positions':
            import json
            position_dict = {}
            for i in range(1, len(player_names_list) + 1):
                pos_value = data.get(f'position_{i}', '0')
                position_dict[str(i)] = float(pos_value)
            position_values = json.dumps(position_dict)
        
        game = Game(
            id=game_id,
            name=data.get('game_name', 'New Game'),
            num_players=num_players,
            num_viewers=int(data.get('num_viewers', 0)),
            player_names=player_names,
            scoring_mode=scoring_mode,
            include_cash=include_cash,
            position_values=position_values
        )
        db.session.add(game)
        db.session.flush()  # Ensure game is in session
        
        # Parse initial distributions
        distribution_mode = data.get('distribution_mode', 'even')
        
        # Create participants and their initial holdings
        participant_links = []
        
        if distribution_mode == 'even':
            # Even distribution: everyone gets cash and shares in all players
            initial_cash = float(data.get('initial_cash', 1000))
            initial_shares = int(data.get('initial_shares', 10))
            
            for i in range(game.num_players):
                participant = Participant(
                    game_id=game.id,
                    name=f"Player {i+1}",
                    role='player',
                    cash=initial_cash
                )
                db.session.add(participant)
                db.session.flush()
                
                # Give initial shares of each tradeable player
                for player_name in player_names_list:
                    holding = Holding(
                        participant_id=participant.id,
                        player_name=player_name,
                        shares=initial_shares
                    )
                    db.session.add(holding)
                
                participant_links.append({
                    'name': participant.name,
                    'role': 'player',
                    'link': url_for('trading_dashboard', token=participant.access_token, _external=True)
                })
            
            for i in range(game.num_viewers):
                participant = Participant(
                    game_id=game.id,
                    name=f"Viewer {i+1}",
                    role='viewer',
                    cash=initial_cash
                )
                db.session.add(participant)
                db.session.flush()
                
                # Viewers also get initial shares
                for player_name in player_names_list:
                    holding = Holding(
                        participant_id=participant.id,
                        player_name=player_name,
                        shares=initial_shares
                    )
                    db.session.add(holding)
                
                participant_links.append({
                    'name': participant.name,
                    'role': 'viewer',
                    'link': url_for('trading_dashboard', token=participant.access_token, _external=True)
                })
        
        else:
            # Own shares only: players get only their own shares, viewers get cash only (no shares)
            own_shares_amount = int(data.get('own_shares_amount', 100))
            player_cash = float(data.get('player_cash', 0))
            viewer_cash = float(data.get('viewer_cash', 1000))
            
            for i in range(game.num_players):
                # Players get their starting cash and only their own shares
                if i < len(player_names_list):
                    own_player_name = player_names_list[i]
                else:
                    own_player_name = None
                
                participant = Participant(
                    game_id=game.id,
                    name=f"Player {i+1}" + (f" ({own_player_name})" if own_player_name else ""),
                    role='player',
                    cash=player_cash
                )
                db.session.add(participant)
                db.session.flush()
                
                # Only give shares in their own player
                if own_player_name:
                    holding = Holding(
                        participant_id=participant.id,
                        player_name=own_player_name,
                        shares=own_shares_amount
                    )
                    db.session.add(holding)
                
                participant_links.append({
                    'name': participant.name,
                    'role': 'player',
                    'link': url_for('trading_dashboard', token=participant.access_token, _external=True)
                })
            
            for i in range(game.num_viewers):
                # Viewers get cash but no shares
                participant = Participant(
                    game_id=game.id,
                    name=f"Viewer {i+1}",
                    role='viewer',
                    cash=viewer_cash
                )
                db.session.add(participant)
                db.session.flush()
                
                # No shares for viewers in this mode
                
                participant_links.append({
                    'name': participant.name,
                    'role': 'viewer',
                    'link': url_for('trading_dashboard', token=participant.access_token, _external=True)
                })
        
        # Create admin participant
        admin = Participant(
            game_id=game.id,
            name="Admin",
            role='admin',
            access_token=game.admin_token,
            cash=0.0
        )
        db.session.add(admin)
        
        # Add admin link at the beginning
        participant_links.insert(0, {
            'name': 'Admin (Game Controller)',
            'role': 'admin',
            'link': url_for('trading_dashboard', token=game.admin_token, _external=True)
        })
        
        db.session.commit()
        
        return render_template('game_created.html', game=game, participant_links=participant_links)
    
    return render_template('create_game.html')


@app.route('/trade/<token>')
def trading_dashboard(token):
    """Main trading dashboard for participants"""
    participant = Participant.query.filter_by(access_token=token).first_or_404()
    game = participant.game
    
    if game.status == 'ended':
        return redirect(url_for('game_results', game_id=game.id))
    
    player_names = [p.strip() for p in game.player_names.split(',') if p.strip()]
    
    # Get participant's holdings
    holdings = {h.player_name: h.shares for h in participant.holdings}
    
    # Get all open orders (anonymous)
    buy_orders = Order.query.filter_by(game_id=game.id, order_type='buy', status='open').all()
    sell_orders = Order.query.filter_by(game_id=game.id, order_type='sell', status='open').all()
    
    # Get participant's own orders
    my_orders = Order.query.filter_by(participant_id=participant.id, status='open').all()
    
    # Get recent transactions
    recent_transactions = Transaction.query.filter_by(game_id=game.id).order_by(Transaction.timestamp.desc()).limit(20).all()
    
    return render_template('trading_dashboard.html',
                          participant=participant,
                          game=game,
                          player_names=player_names,
                          holdings=holdings,
                          buy_orders=buy_orders,
                          sell_orders=sell_orders,
                          my_orders=my_orders,
                          recent_transactions=recent_transactions)


@app.route('/api/place-order', methods=['POST'])
def place_order():
    """API endpoint to place a buy or sell order"""
    data = request.json
    token = data.get('token')
    
    participant = Participant.query.filter_by(access_token=token).first()
    if not participant:
        return jsonify({'error': 'Invalid token'}), 401
    
    game = participant.game
    if game.status == 'ended':
        return jsonify({'error': 'Game has ended'}), 400
    
    order_type = data.get('order_type')
    player_name = data.get('player_name')
    price = float(data.get('price', 0))
    shares = int(data.get('shares', 0))
    
    if price <= 0 or shares <= 0:
        return jsonify({'error': 'Invalid price or shares'}), 400
    
    # Validate the order
    if order_type == 'sell':
        # Check if participant has enough shares
        holding = Holding.query.filter_by(participant_id=participant.id, player_name=player_name).first()
        available_shares = holding.shares if holding else 0
        
        # Subtract shares already committed in open sell orders
        open_sell_orders = Order.query.filter_by(
            participant_id=participant.id,
            player_name=player_name,
            order_type='sell',
            status='open'
        ).all()
        committed_shares = sum(order.shares for order in open_sell_orders)
        available_shares -= committed_shares
        
        if available_shares < shares:
            return jsonify({'error': f'Not enough shares. You have {holding.shares if holding else 0} shares, but {committed_shares} are already in open sell orders. Available: {available_shares}'}), 400
    elif order_type == 'buy':
        # Check if participant has enough cash
        total_cost = price * shares
        
        # Subtract cash already committed in open buy orders
        open_buy_orders = Order.query.filter_by(
            participant_id=participant.id,
            status='open',
            order_type='buy'
        ).all()
        committed_cash = sum(order.price * order.shares for order in open_buy_orders)
        available_cash = participant.cash - committed_cash
        
        if available_cash < total_cost:
            return jsonify({'error': f'Not enough cash. You have ${participant.cash:.2f}, but ${committed_cash:.2f} is already in open buy orders. Available: ${available_cash:.2f}'}), 400
    else:
        return jsonify({'error': 'Invalid order type'}), 400
    
    # Create the order
    order = Order(
        game_id=game.id,
        participant_id=participant.id,
        order_type=order_type,
        player_name=player_name,
        price=price,
        shares=shares
    )
    db.session.add(order)
    db.session.commit()
    
    return jsonify({'success': True, 'order_id': order.id})


@app.route('/api/execute-order', methods=['POST'])
def execute_order():
    """API endpoint to execute (accept) an existing order"""
    data = request.json
    token = data.get('token')
    order_id = data.get('order_id')
    shares_to_execute = data.get('shares')  # Optional: partial fill
    
    participant = Participant.query.filter_by(access_token=token).first()
    if not participant:
        return jsonify({'error': 'Invalid token'}), 401
    
    order = Order.query.get(order_id)
    if not order or order.status != 'open':
        return jsonify({'error': 'Order not available'}), 400
    
    if order.participant_id == participant.id:
        return jsonify({'error': 'Cannot execute your own order'}), 400
    
    game = participant.game
    if game.status == 'ended':
        return jsonify({'error': 'Game has ended'}), 400
    
    # Default to full order if shares not specified
    if shares_to_execute is None:
        shares_to_execute = order.shares
    else:
        shares_to_execute = int(shares_to_execute)
    
    # Validate shares amount
    if shares_to_execute <= 0:
        return jsonify({'error': 'Invalid number of shares'}), 400
    
    if shares_to_execute > order.shares:
        return jsonify({'error': f'Order only has {order.shares} shares available'}), 400
    
    order_creator = Participant.query.get(order.participant_id)
    
    if order.order_type == 'sell':
        # Someone is selling, participant is buying
        buyer = participant
        seller = order_creator
        
        total_cost = order.price * shares_to_execute
        if buyer.cash < total_cost:
            return jsonify({'error': 'Not enough cash'}), 400
        
        # Check seller still has shares
        seller_holding = Holding.query.filter_by(participant_id=seller.id, player_name=order.player_name).first()
        if not seller_holding or seller_holding.shares < shares_to_execute:
            order.status = 'cancelled'
            db.session.commit()
            return jsonify({'error': 'Seller no longer has shares'}), 400
        
        # Execute trade
        buyer.cash -= total_cost
        seller.cash += total_cost
        
        seller_holding.shares -= shares_to_execute
        
        buyer_holding = Holding.query.filter_by(participant_id=buyer.id, player_name=order.player_name).first()
        if buyer_holding:
            buyer_holding.shares += shares_to_execute
        else:
            buyer_holding = Holding(participant_id=buyer.id, player_name=order.player_name, shares=shares_to_execute)
            db.session.add(buyer_holding)
        
    else:  # buy order
        # Someone wants to buy, participant is selling
        buyer = order_creator
        seller = participant
        
        total_cost = order.price * shares_to_execute
        
        # Check seller has shares
        seller_holding = Holding.query.filter_by(participant_id=seller.id, player_name=order.player_name).first()
        if not seller_holding or seller_holding.shares < shares_to_execute:
            return jsonify({'error': 'Not enough shares'}), 400
        
        # Check buyer still has cash
        if buyer.cash < total_cost:
            order.status = 'cancelled'
            db.session.commit()
            return jsonify({'error': 'Buyer no longer has cash'}), 400
        
        # Execute trade
        buyer.cash -= total_cost
        seller.cash += total_cost
        
        seller_holding.shares -= shares_to_execute
        
        buyer_holding = Holding.query.filter_by(participant_id=buyer.id, player_name=order.player_name).first()
        if buyer_holding:
            buyer_holding.shares += shares_to_execute
        else:
            buyer_holding = Holding(participant_id=buyer.id, player_name=order.player_name, shares=shares_to_execute)
            db.session.add(buyer_holding)
    
    # Record transaction
    transaction = Transaction(
        game_id=game.id,
        buyer_id=buyer.id,
        seller_id=seller.id,
        player_name=order.player_name,
        price=order.price,
        shares=shares_to_execute
    )
    db.session.add(transaction)
    
    # Update order: reduce shares or mark as filled
    order.shares -= shares_to_execute
    if order.shares == 0:
        order.status = 'filled'
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/cancel-all-orders', methods=['POST'])
def cancel_all_orders():
    """API endpoint to cancel all orders for a participant"""
    data = request.json
    token = data.get('token')
    order_type = data.get('order_type')  # 'buy', 'sell', or 'all'
    
    participant = Participant.query.filter_by(access_token=token).first()
    if not participant:
        return jsonify({'error': 'Invalid token'}), 401
    
    # Build query for participant's open orders
    query = Order.query.filter_by(
        participant_id=participant.id,
        status='open'
    )
    
    # Filter by order type if specified
    if order_type in ['buy', 'sell']:
        query = query.filter_by(order_type=order_type)
    
    # Cancel all matching orders
    orders = query.all()
    count = len(orders)
    
    for order in orders:
        order.status = 'cancelled'
    
    db.session.commit()
    
    return jsonify({'success': True, 'cancelled_count': count})


@app.route('/api/cancel-order', methods=['POST'])
def cancel_order():
    """API endpoint to cancel an order"""
    data = request.json
    token = data.get('token')
    order_id = data.get('order_id')
    
    participant = Participant.query.filter_by(access_token=token).first()
    if not participant:
        return jsonify({'error': 'Invalid token'}), 401
    
    order = Order.query.get(order_id)
    if not order or order.participant_id != participant.id:
        return jsonify({'error': 'Order not found'}), 404
    
    if order.status != 'open':
        return jsonify({'error': 'Order cannot be cancelled'}), 400
    
    order.status = 'cancelled'
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/end-game', methods=['POST'])
def end_game():
    """API endpoint to end a game and determine winner - ADMIN ONLY"""
    import json
    data = request.json
    token = data.get('token')
    
    participant = Participant.query.filter_by(access_token=token).first()
    if not participant:
        return jsonify({'error': 'Invalid token'}), 401
    
    # Check if participant is admin
    if participant.role != 'admin':
        return jsonify({'error': 'Only admin can end the game'}), 403
    
    game = participant.game
    if game.status == 'ended':
        return jsonify({'error': 'Game already ended'}), 400
    
    # Cancel all open orders
    Order.query.filter_by(game_id=game.id, status='open').update({'status': 'cancelled'})
    
    # Determine winner based on scoring mode
    participants = Participant.query.filter_by(game_id=game.id, role='player').all()
    winner = None
    
    if game.scoring_mode == 'outright_winner':
        # Original logic: winner based on shares in winning player
        winning_player = data.get('winning_player')
        max_shares = -1
        
        for p in participants:
            holding = Holding.query.filter_by(participant_id=p.id, player_name=winning_player).first()
            shares = holding.shares if holding else 0
            if shares > max_shares:
                max_shares = shares
                winner = p
                
    elif game.scoring_mode == 'final_points':
        # Each share worth the player's final score
        final_scores = data.get('final_scores', {})  # {player_name: score}
        game.final_scores = json.dumps(final_scores)
        
        max_value = -1
        for p in participants:
            total_value = 0
            for holding in p.holdings:
                player_score = float(final_scores.get(holding.player_name, 0))
                total_value += holding.shares * player_score
            
            if game.include_cash:
                total_value += p.cash
            
            if total_value > max_value:
                max_value = total_value
                winner = p
                
    elif game.scoring_mode == 'top_positions':
        # Each position has a set value
        final_positions = data.get('final_positions', {})  # {player_name: position}
        position_values = json.loads(game.position_values)
        
        max_value = -1
        for p in participants:
            total_value = 0
            for holding in p.holdings:
                position = str(final_positions.get(holding.player_name, 999))
                position_value = float(position_values.get(position, 0))
                total_value += holding.shares * position_value
            
            if game.include_cash:
                total_value += p.cash
            
            if total_value > max_value:
                max_value = total_value
                winner = p
    
    game.status = 'ended'
    game.winner_id = winner.id if winner else None
    db.session.commit()
    
    return jsonify({
        'success': True,
        'winner': winner.name if winner else None,
        'redirect': url_for('game_results', game_id=game.id)
    })


@app.route('/results/<game_id>')
def game_results(game_id):
    """Display final results of a game"""
    game = Game.query.get_or_404(game_id)
    
    player_names = [p.strip() for p in game.player_names.split(',') if p.strip()]
    participants = Participant.query.filter_by(game_id=game.id).all()
    
    # Build results data
    results = []
    for p in participants:
        holdings = {h.player_name: h.shares for h in p.holdings}
        total_shares = sum(holdings.values())
        results.append({
            'participant': p,
            'holdings': holdings,
            'total_shares': total_shares
        })
    
    winner = Participant.query.get(game.winner_id) if game.winner_id else None
    
    return render_template('results.html',
                          game=game,
                          player_names=player_names,
                          results=results,
                          winner=winner)


@app.route('/api/game-state/<token>')
def get_game_state(token):
    """API endpoint to get current game state (for real-time updates)"""
    participant = Participant.query.filter_by(access_token=token).first()
    if not participant:
        return jsonify({'error': 'Invalid token'}), 401
    
    game = participant.game
    player_names = [p.strip() for p in game.player_names.split(',') if p.strip()]
    
    # Get holdings
    holdings = {h.player_name: h.shares for h in participant.holdings}
    
    # Get orders
    buy_orders = []
    for o in Order.query.filter_by(game_id=game.id, order_type='buy', status='open').all():
        buy_orders.append({
            'id': o.id,
            'player_name': o.player_name,
            'price': o.price,
            'shares': o.shares,
            'is_mine': o.participant_id == participant.id
        })
    
    sell_orders = []
    for o in Order.query.filter_by(game_id=game.id, order_type='sell', status='open').all():
        sell_orders.append({
            'id': o.id,
            'player_name': o.player_name,
            'price': o.price,
            'shares': o.shares,
            'is_mine': o.participant_id == participant.id
        })
    
    recent_transactions = []
    for t in Transaction.query.filter_by(game_id=game.id).order_by(Transaction.timestamp.desc()).limit(20).all():
        # Determine if this participant was buyer or seller
        transaction_type = None
        if t.buyer_id == participant.id:
            transaction_type = 'buy'
        elif t.seller_id == participant.id:
            transaction_type = 'sell'
        
        recent_transactions.append({
            'player_name': t.player_name,
            'price': t.price,
            'shares': t.shares,
            'timestamp': t.timestamp.isoformat(),
            'type': transaction_type,
            'is_mine': transaction_type is not None
        })
    
    return jsonify({
        'game_status': game.status,
        'cash': participant.cash,
        'holdings': holdings,
        'buy_orders': buy_orders,
        'sell_orders': sell_orders,
        'recent_transactions': recent_transactions,
        'player_names': player_names
    })


@app.route('/api/market-metrics/<token>')
def get_market_metrics(token):
    """API endpoint to get market analytics and metrics"""
    participant = Participant.query.filter_by(access_token=token).first()
    if not participant:
        return jsonify({'error': 'Invalid token'}), 401
    
    game = participant.game
    player_names = [p.strip() for p in game.player_names.split(',') if p.strip()]
    
    # Get all transactions for the game
    all_transactions = Transaction.query.filter_by(game_id=game.id).order_by(Transaction.timestamp.asc()).all()
    
    # Calculate metrics per player
    metrics = {}
    
    for player_name in player_names:
        player_transactions = [t for t in all_transactions if t.player_name == player_name]
        
        # Price history
        price_history = []
        for t in player_transactions:
            price_history.append({
                'timestamp': t.timestamp.isoformat(),
                'price': t.price,
                'volume': t.shares
            })
        
        # Current market prices (from open orders)
        buy_orders = Order.query.filter_by(
            game_id=game.id, 
            player_name=player_name, 
            order_type='buy', 
            status='open'
        ).order_by(Order.price.desc()).all()
        
        sell_orders = Order.query.filter_by(
            game_id=game.id, 
            player_name=player_name, 
            order_type='sell', 
            status='open'
        ).order_by(Order.price.asc()).all()
        
        highest_bid = buy_orders[0].price if buy_orders else None
        lowest_ask = sell_orders[0].price if sell_orders else None
        
        # Calculate statistics
        if player_transactions:
            prices = [t.price for t in player_transactions]
            volumes = [t.shares for t in player_transactions]
            
            last_price = prices[-1]
            avg_price = sum(prices) / len(prices)
            high_price = max(prices)
            low_price = min(prices)
            total_volume = sum(volumes)
            
            # Calculate price change
            if len(prices) > 1:
                first_price = prices[0]
                price_change = last_price - first_price
                price_change_percent = (price_change / first_price * 100) if first_price > 0 else 0
            else:
                price_change = 0
                price_change_percent = 0
        else:
            last_price = None
            avg_price = None
            high_price = None
            low_price = None
            total_volume = 0
            price_change = 0
            price_change_percent = 0
        
        # Order book depth
        order_book = {
            'bids': [{'price': o.price, 'shares': o.shares} for o in buy_orders[:10]],
            'asks': [{'price': o.price, 'shares': o.shares} for o in sell_orders[:10]]
        }
        
        # Trading volume over time (grouped by time periods)
        volume_history = []
        if player_transactions:
            # Group by hour for volume chart
            from collections import defaultdict
            volume_by_hour = defaultdict(int)
            for t in player_transactions:
                hour_key = t.timestamp.replace(minute=0, second=0, microsecond=0)
                volume_by_hour[hour_key] += t.shares
            
            for hour, vol in sorted(volume_by_hour.items()):
                volume_history.append({
                    'timestamp': hour.isoformat(),
                    'volume': vol
                })
        
        metrics[player_name] = {
            'last_price': last_price,
            'price_change': price_change,
            'price_change_percent': price_change_percent,
            'avg_price': avg_price,
            'high_price': high_price,
            'low_price': low_price,
            'total_volume': total_volume,
            'highest_bid': highest_bid,
            'lowest_ask': lowest_ask,
            'spread': (lowest_ask - highest_bid) if (highest_bid and lowest_ask) else None,
            'price_history': price_history,
            'volume_history': volume_history,
            'order_book': order_book,
            'transaction_count': len(player_transactions)
        }
    
    # Market overview
    total_trades = len(all_transactions)
    total_volume = sum(t.shares for t in all_transactions)
    
    return jsonify({
        'metrics': metrics,
        'market_overview': {
            'total_trades': total_trades,
            'total_volume': total_volume,
            'active_players': len(player_names)
        }
    })


# ============== Initialize Database ==============

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
