#!/usr/bin/env python3
"""
Predict Price Changes

Uses trained model to predict which players will rise/fall in price.
Runs daily to give Hugo 6-12 hour warning for pre-emptive transfers.

Optimized for Raspberry Pi 3 - fast inference.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.price_change import PriceChangePredictor
from agents.data_collector import DataCollector
from data.database import Database
from notifications.slack import SlackNotifier
import logging
import os

logger = logging.getLogger('ron_clanker.price_predictions')


async def predict_prices():
    """Generate price change predictions for all players."""

    start_time = datetime.now()
    today = date.today()
    prediction_date = today + timedelta(days=1)  # Predict for tomorrow

    print("\n" + "=" * 80)
    print("PRICE CHANGE PREDICTIONS")
    print("=" * 80)
    print(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Predicting for: {prediction_date}")

    db = Database()

    # Check if model exists
    model_path = project_root / "models" / "price_model.pkl"
    if not model_path.exists():
        print(f"\n❌ No trained model found: {model_path}")
        print(f"   Train model first:")
        print(f"   venv/bin/python scripts/train_price_model.py")
        return 1

    # Load model
    print(f"\n📊 Loading model from {model_path.name}...")
    try:
        predictor = PriceChangePredictor.load(str(model_path))
        print(f"✓ Model loaded: {predictor.MODEL_VERSION}")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return 1

    # Get latest player data
    collector = DataCollector()

    try:
        print("\n📡 Fetching latest player data...")
        fpl_data = await collector.update_all_data()

        if not fpl_data:
            print("❌ Failed to fetch FPL data")
            return 1

        players = fpl_data.get('players', [])
        print(f"✓ Retrieved {len(players)} players")

        # Make predictions
        print("\n" + "-" * 80)
        print("GENERATING PREDICTIONS")
        print("-" * 80)

        predictions = []
        rises = []
        falls = []

        prediction_start = datetime.now()

        for i, player in enumerate(players):
            if (i + 1) % 100 == 0:
                print(f"  Processing {i + 1}/{len(players)}...")

            try:
                predicted_change, confidence = predictor.predict(player)

                # Only store significant predictions (confidence > 0.5)
                if confidence > 0.5:
                    prediction_data = {
                        'player_id': player['id'],
                        'player_name': player['web_name'],
                        'team': player['team_name'],
                        'position': player['element_type'],
                        'price': player['now_cost'] / 10.0,
                        'predicted_change': predicted_change,
                        'confidence': confidence,
                        'net_transfers': player.get('transfers_in', 0) - player.get('transfers_out', 0),
                        'ownership': float(player.get('selected_by_percent', 0.0))
                    }

                    predictions.append(prediction_data)

                    if predicted_change == 1:
                        rises.append(prediction_data)
                    elif predicted_change == -1:
                        falls.append(prediction_data)

                    # Store in database
                    db.execute_update("""
                        INSERT INTO price_predictions (
                            player_id, prediction_for_date,
                            predicted_change, confidence,
                            model_version, features
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        player['id'],
                        prediction_date,
                        predicted_change,
                        confidence,
                        predictor.MODEL_VERSION,
                        json.dumps({
                            'net_transfers': prediction_data['net_transfers'],
                            'ownership': prediction_data['ownership'],
                            'form': float(player.get('form', 0.0))
                        })
                    ))

            except Exception as e:
                logger.warning(f"Prediction error for player {player['id']}: {e}")

        prediction_duration = (datetime.now() - prediction_start).total_seconds()

        print(f"\n✓ Generated {len(predictions)} predictions")
        print(f"  Inference time: {prediction_duration:.2f} seconds")
        print(f"  Average: {(prediction_duration / len(players) * 1000):.1f}ms per player")

        # Show results
        print("\n" + "-" * 80)
        print("PREDICTION SUMMARY")
        print("-" * 80)

        print(f"\nPredicted RISES: {len(rises)}")
        print(f"Predicted FALLS: {len(falls)}")
        print(f"Predicted HOLDS: {len(players) - len(predictions)}")

        # Show top predicted rises
        if rises:
            rises.sort(key=lambda x: x['confidence'], reverse=True)
            print("\n" + "-" * 80)
            print("TOP 10 PREDICTED PRICE RISES")
            print("-" * 80)
            print()

            for i, player in enumerate(rises[:10], 1):
                print(f"{i:2d}. {player['player_name']:20s} ({player['team']:15s}) "
                      f"£{player['price']:.1f}m | "
                      f"Confidence: {player['confidence']:.0%} | "
                      f"Net: {player['net_transfers']:>8,} | "
                      f"Own: {player['ownership']:>5.1f}%")

        # Show top predicted falls
        if falls:
            falls.sort(key=lambda x: x['confidence'], reverse=True)
            print("\n" + "-" * 80)
            print("TOP 10 PREDICTED PRICE FALLS")
            print("-" * 80)
            print()

            for i, player in enumerate(falls[:10], 1):
                print(f"{i:2d}. {player['player_name']:20s} ({player['team']:15s}) "
                      f"£{player['price']:.1f}m | "
                      f"Confidence: {player['confidence']:.0%} | "
                      f"Net: {player['net_transfers']:>8,} | "
                      f"Own: {player['ownership']:>5.1f}%")

        # Hugo integration hint
        if rises or falls:
            print("\n" + "-" * 80)
            print("TRANSFER RECOMMENDATIONS")
            print("-" * 80)

            high_conf_rises = [p for p in rises if p['confidence'] > 0.75]
            high_conf_falls = [p for p in falls if p['confidence'] > 0.75]

            if high_conf_rises:
                print(f"\n💰 {len(high_conf_rises)} HIGH CONFIDENCE rises (>75%)")
                print("   Consider transferring IN before price rise:")
                for player in high_conf_rises[:5]:
                    print(f"     • {player['player_name']} (£{player['price']:.1f}m)")

            if high_conf_falls:
                print(f"\n📉 {len(high_conf_falls)} HIGH CONFIDENCE falls (>75%)")
                print("   Consider transferring OUT before price fall:")
                for player in high_conf_falls[:5]:
                    print(f"     • {player['player_name']} (£{player['price']:.1f}m)")

        duration = (datetime.now() - start_time).total_seconds()

        print("\n" + "=" * 80)
        print("PREDICTIONS COMPLETE")
        print("=" * 80)
        print(f"Total duration: {duration:.1f} seconds")
        print(f"Predictions stored in database")
        print(f"\nNext: Wait for actual price changes (02:00 AM)")
        print(f"Then: Outcomes are settled by the nightly snapshot run (verify_price_predictions in collect_price_snapshots.py)")

        # Dry/technical report -> the private ops channel
        if rises or falls:
            try:
                lines = [f"Price predictions for {prediction_date}:"]
                for r in rises[:10]:
                    lines.append(f"  ▲ {r['player_name']} £{r['price']:.1f}m "
                                 f"({r['confidence']:.0%})")
                for f_ in falls[:10]:
                    lines.append(f"  ▼ {f_['player_name']} £{f_['price']:.1f}m "
                                 f"({f_['confidence']:.0%})")
                SlackNotifier().send_ops("\n".join(lines),
                                         context="price-predict")
            except Exception as e:
                logger.warning(f"Failed to send ops notification: {e}")

        return 0

    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")

        try:
            SlackNotifier().send_ops(f"Price predictions failed: {e}",
                                     context="price-predict")
        except Exception:
            pass  # Don't fail on notification failure

        return 1

    finally:
        await collector.close()


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(predict_prices())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nPredictions cancelled.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
