#!/bin/bash
# Quick start script for My AI Cycling Coach

echo "🚀 My AI Cycling Coach - Setup"
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

# Install desktop integration (icon + .desktop file)
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON_SRC="$INSTALL_DIR/assets/icon.svg"
ICON_DEST="$HOME/.local/share/icons/my-ai-cycling-coach.svg"
DESKTOP_DEST="$HOME/.local/share/applications/my-ai-cycling-coach.desktop"

mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps" "$HOME/.local/share/applications"
cp "$ICON_SRC" "$ICON_DEST"
cp "$ICON_SRC" "$HOME/.local/share/icons/hicolor/scalable/apps/my-ai-cycling-coach.svg"

cat > "$DESKTOP_DEST" <<EOF
[Desktop Entry]
Name=My AI Cycling Coach
Exec=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/main.py
Icon=my-ai-cycling-coach
Type=Application
Categories=Sports;
StartupWMClass=my-ai-cycling-coach
EOF

echo "✓ Desktop icon installed"

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 To run the application:"
echo "   source venv/bin/activate"
echo "   python main.py"
echo ""
