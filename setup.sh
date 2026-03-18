#!/bin/bash
# Quick start script for FIT Data Visualizer

echo "🚀 FIT Data Visualizer - Setup"
echo "================================"

# Check Python version
python3_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python $python3_version detected"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "❌ Failed to activate virtual environment"
    exit 1
fi

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Failed to install requirements"
    exit 1
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 To run the application:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
echo "💡 To load FIT files:"
echo "   1. Copy .fit files to the 'data/' directory, or"
echo "   2. Click 'Open Folder' in the application"
echo ""
