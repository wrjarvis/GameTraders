"""
Create a test game with fake data for testing
"""
import random
from datetime import datetime, timedelta
from app import app, db, Game, Participant, Holding, Order, Transaction
import uuid

def create_test_game():
    with app.app_context():
        # Create game
        game_id = str(uuid.uuid4())
        player_names = "Alice,Bob,Charlie"
        
        game = Game(
            id=game_id,
            name="Test Game - 2 Week Trading Simulation",
            num_players=3,
            num_viewers=0,
            player_names=player_names,
            scoring_mode='final_points',
            include_cash=True,
            created_at=datetime.utcnow() - timedelta(days=14)
        )
        db.session.add(game)
        db.session.flush()
        
        # Create participants
        traders = []
        player_list = ["Alice", "Bob", "Charlie"]
        
        for i, name in enumerate(["Player 1", "Player 2", "Player 3"]):
            participant = Participant(
                game_id=game.id,
                name=name,
                role='player',
                cash=1000.0
            )
            db.session.add(participant)
            db.session.flush()
            
            # Give each player initial shares in all board game players
            for player_name in player_list:
                holding = Holding(
                    participant_id=participant.id,
                    player_name=player_name,
                    shares=10
                )
                db.session.add(holding)
            
            traders.append(participant)
        
        # Create admin
        admin = Participant(
            game_id=game.id,
            name="Admin",
            role='admin',
            access_token=game.admin_token,
            cash=0.0
        )
        db.session.add(admin)
        db.session.flush()
        
        # Generate 2 weeks of trading activity
        base_prices = {"Alice": 10.0, "Bob": 10.0, "Charlie": 10.0}
        current_time = game.created_at
        
        # Create ~100 transactions over 2 weeks
        for day in range(14):
            # 5-10 trades per day
            num_trades = random.randint(5, 10)
            
            for _ in range(num_trades):
                # Random time during the day
                trade_time = current_time + timedelta(
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                
                # Pick random buyer and seller
                buyer = random.choice(traders)
                seller = random.choice([t for t in traders if t.id != buyer.id])
                
                # Pick random player to trade
                player_name = random.choice(player_list)
                
                # Check if seller has shares
                seller_holding = Holding.query.filter_by(
                    participant_id=seller.id,
                    player_name=player_name
                ).first()
                
                if not seller_holding or seller_holding.shares < 1:
                    continue
                
                # Random price variation (+/- 20% from base)
                price_variation = random.uniform(0.8, 1.2)
                price = round(base_prices[player_name] * price_variation, 2)
                
                # Slowly increase base prices over time
                base_prices[player_name] *= random.uniform(1.0, 1.05)
                
                # Random shares (1-3)
                shares = min(random.randint(1, 3), seller_holding.shares)
                total_cost = price * shares
                
                # Check buyer has enough cash
                if buyer.cash < total_cost:
                    continue
                
                # Execute trade
                buyer.cash -= total_cost
                seller.cash += total_cost
                
                # Update seller shares
                seller_holding.shares -= shares
                
                # Update buyer shares
                buyer_holding = Holding.query.filter_by(
                    participant_id=buyer.id,
                    player_name=player_name
                ).first()
                
                if buyer_holding:
                    buyer_holding.shares += shares
                else:
                    buyer_holding = Holding(
                        participant_id=buyer.id,
                        player_name=player_name,
                        shares=shares
                    )
                    db.session.add(buyer_holding)
                
                # Record transaction
                transaction = Transaction(
                    game_id=game.id,
                    buyer_id=buyer.id,
                    seller_id=seller.id,
                    player_name=player_name,
                    shares=shares,
                    price=price,
                    timestamp=trade_time
                )
                db.session.add(transaction)
            
            # Move to next day
            current_time += timedelta(days=1)
        
        # Add some open orders
        for trader in traders:
            # 1-2 open orders per player
            for _ in range(random.randint(1, 2)):
                order_type = random.choice(['buy', 'sell'])
                player_name = random.choice(player_list)
                
                if order_type == 'sell':
                    # Check if they have shares
                    holding = Holding.query.filter_by(
                        participant_id=trader.id,
                        player_name=player_name
                    ).first()
                    if not holding or holding.shares < 1:
                        continue
                
                price = round(base_prices[player_name] * random.uniform(0.9, 1.1), 2)
                shares = random.randint(1, 3)
                
                order = Order(
                    game_id=game.id,
                    participant_id=trader.id,
                    player_name=player_name,
                    order_type=order_type,
                    shares=shares,
                    price=price,
                    status='open'
                )
                db.session.add(order)
        
        db.session.commit()
        
        print("✅ Test game created successfully!")
        print(f"\nGame: {game.name}")
        print(f"Created: {game.created_at}")
        print(f"\n{'='*60}")
        print("PARTICIPANT LINKS:")
        print(f"{'='*60}\n")
        
        print(f"🔑 ADMIN LINK:")
        print(f"   http://localhost:5000/trade/{game.admin_token}")
        print(f"\n{'='*60}\n")
        
        for i, trader in enumerate(traders):
            print(f"👤 {trader.name}:")
            print(f"   http://localhost:5000/trade/{trader.access_token}")
            print(f"   Cash: ${trader.cash:.2f}")
            holdings = Holding.query.filter_by(participant_id=trader.id).all()
            for h in holdings:
                print(f"   {h.player_name}: {h.shares} shares")
            print()
        
        print(f"{'='*60}")
        
        # Print some stats
        total_transactions = Transaction.query.filter_by(game_id=game.id).count()
        total_orders = Order.query.filter_by(game_id=game.id, status='open').count()
        
        print(f"\n📊 STATISTICS:")
        print(f"   Total Transactions: {total_transactions}")
        print(f"   Open Orders: {total_orders}")
        print(f"   Final Prices: Alice=${base_prices['Alice']:.2f}, Bob=${base_prices['Bob']:.2f}, Charlie=${base_prices['Charlie']:.2f}")
        print(f"\n{'='*60}\n")

if __name__ == '__main__':
    create_test_game()
