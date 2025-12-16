#!/bin/bash
# Debug script to check filestore configuration

echo "=========================================="
echo "FILESTORE DEBUGGING SCRIPT"
echo "=========================================="
echo ""

echo "1. Checking if OLD Odoo filestore exists and has files:"
echo "---"
if [ -d "/home/odoo/.local/share/Odoo/filestore/promatik" ]; then
    echo "✅ /home/odoo/.local/share/Odoo/filestore/promatik EXISTS"
    file_count=$(find /home/odoo/.local/share/Odoo/filestore/promatik -type f | wc -l)
    echo "   Files found: $file_count"
    echo "   Sample files:"
    find /home/odoo/.local/share/Odoo/filestore/promatik -type f | head -5
else
    echo "❌ /home/odoo/.local/share/Odoo/filestore/promatik DOES NOT EXIST"
fi
echo ""

echo "2. Checking if NEW Sage directory exists:"
echo "---"
if [ -d "/home/odoo/.local/share/Sage" ]; then
    echo "✅ /home/odoo/.local/share/Sage EXISTS"
    if [ -L "/home/odoo/.local/share/Sage" ]; then
        echo "   It's a SYMLINK pointing to:"
        readlink -f /home/odoo/.local/share/Sage
    else
        echo "   It's a REAL DIRECTORY (not a symlink)"
        if [ -d "/home/odoo/.local/share/Sage/filestore/promatik" ]; then
            file_count=$(find /home/odoo/.local/share/Sage/filestore/promatik -type f 2>/dev/null | wc -l)
            echo "   Files in Sage filestore: $file_count"
        else
            echo "   ❌ No filestore directory inside Sage"
        fi
    fi
else
    echo "❌ /home/odoo/.local/share/Sage DOES NOT EXIST"
fi
echo ""

echo "3. Checking specific file from error:"
echo "---"
test_file="23/23b035552184e0a9502d80756dd8f02e0946aab1"
if [ -f "/home/odoo/.local/share/Odoo/filestore/promatik/$test_file" ]; then
    echo "✅ File EXISTS in OLD location: /home/odoo/.local/share/Odoo/filestore/promatik/$test_file"
else
    echo "❌ File NOT FOUND in OLD location"
fi

if [ -f "/home/odoo/.local/share/Sage/filestore/promatik/$test_file" ]; then
    echo "✅ File ACCESSIBLE via Sage path: /home/odoo/.local/share/Sage/filestore/promatik/$test_file"
else
    echo "❌ File NOT ACCESSIBLE via Sage path"
fi
echo ""

echo "4. Checking Odoo config file:"
echo "---"
config_file="/etc/odoo.conf"
if [ -f "$config_file" ]; then
    echo "Config file: $config_file"
    echo "data_dir setting:"
    grep -E "^data_dir" "$config_file" || echo "   (no data_dir line found - using default)"
else
    # Try alternative locations
    for alt_config in "/etc/odoo/odoo.conf" "/home/odoo/.odoorc" "/home/odoo/odoo.conf"; do
        if [ -f "$alt_config" ]; then
            echo "Config file: $alt_config"
            echo "data_dir setting:"
            grep -E "^data_dir" "$alt_config" || echo "   (no data_dir line found - using default)"
            config_file="$alt_config"
            break
        fi
    done
fi
echo ""

echo "5. Checking Odoo service status:"
echo "---"
systemctl status odoo --no-pager | head -10
echo ""

echo "6. Checking recent Odoo logs for data_dir:"
echo "---"
echo "Looking for data_dir initialization in logs..."
journalctl -u odoo --since "5 minutes ago" | grep -i "data_dir\|filestore" | tail -5 || echo "(no relevant logs found)"
echo ""

echo "=========================================="
echo "RECOMMENDATIONS:"
echo "=========================================="

if [ ! -d "/home/odoo/.local/share/Odoo/filestore/promatik" ]; then
    echo "⚠️  CRITICAL: Old filestore not found! Files may have been moved or deleted."
elif [ ! -L "/home/odoo/.local/share/Sage" ]; then
    echo "⚠️  Symlink not created or is a real directory. Run:"
    echo "   sudo systemctl stop odoo"
    echo "   sudo rm -rf /home/odoo/.local/share/Sage"
    echo "   sudo -u odoo ln -s /home/odoo/.local/share/Odoo /home/odoo/.local/share/Sage"
    echo "   sudo systemctl start odoo"
elif grep -q "^data_dir.*Sage" "$config_file" 2>/dev/null; then
    echo "⚠️  Config has data_dir pointing to Sage. Edit $config_file and either:"
    echo "   A) Change to: data_dir = /home/odoo/.local/share/Odoo"
    echo "   B) Remove the data_dir line entirely"
    echo "   Then: sudo systemctl restart odoo"
elif grep -q "^data_dir" "$config_file" 2>/dev/null; then
    current_dir=$(grep "^data_dir" "$config_file" | cut -d'=' -f2 | tr -d ' ')
    echo "✅ data_dir is set to: $current_dir"
    echo "   Verify this is correct and restart: sudo systemctl restart odoo"
else
    echo "⚠️  No data_dir in config. Odoo will use default based on product_name."
    echo "   Since product_name='Sage', it will look in /home/odoo/.local/share/Sage"
    echo "   Make sure the symlink is working!"
fi

echo ""
echo "=========================================="
