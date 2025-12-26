#!/usr/bin/env python3
"""
Train Transformer Model for FPL Prediction

Trains the transformer model that learns player embeddings from form sequences.
Recommended to run weekly after each gameweek completes.

Usage:
    python scripts/train_transformer.py
    python scripts/train_transformer.py --epochs 50
    python scripts/train_transformer.py --check-gpu
"""

import sys
from pathlib import Path
import argparse
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(description='Train FPL Transformer Model')
    parser.add_argument('--epochs', type=int, default=30, help='Number of training epochs (default: 30)')
    parser.add_argument('--batch-size', type=int, default=128, help='Batch size (default: 128)')
    parser.add_argument('--check-gpu', action='store_true', help='Just check GPU status and exit')
    parser.add_argument('--db', type=str, default='./data/ron_clanker.db', help='Database path')
    args = parser.parse_args()

    # Check GPU
    import torch
    print(f"\n🖥️  GPU Status:")
    print(f"   CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        print("   ⚠️  No GPU detected - training will be slow on CPU")

    if args.check_gpu:
        return

    # Import after GPU check
    from data.database import Database
    from ml.prediction.transformer_model import TransformerPredictor, DEVICE

    print(f"\n🤖 Transformer Training")
    print(f"   Device: {DEVICE}")
    print(f"   Epochs: {args.epochs}")
    print(f"   Batch size: {args.batch_size}")
    print(f"   Database: {args.db}")

    # Initialize
    db = Database(args.db)
    predictor = TransformerPredictor()

    # Train
    print(f"\n📊 Starting training...")
    start_time = time.time()

    predictor.train(
        database=db,
        epochs=args.epochs,
        batch_size=args.batch_size
    )

    elapsed = time.time() - start_time
    print(f"\n✅ Training complete in {elapsed:.1f}s ({elapsed/60:.1f} mins)")

    # Show embedding stats
    embeddings = predictor.model.get_player_embeddings()
    print(f"\n📈 Model Stats:")
    print(f"   Player embeddings: {embeddings.shape[0]} players × {embeddings.shape[1]} dimensions")
    print(f"   Model saved to: models/transformer/")

    print(f"\n🎯 Transformer is now integrated into the prediction ensemble.")
    print(f"   It will be used automatically in pre_deadline_selection.py")


if __name__ == '__main__':
    main()
