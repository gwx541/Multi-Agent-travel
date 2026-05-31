package com.travelagent.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.Settings;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * 「所有文件访问」权限的检查与申请。
 *
 * 本地记忆文件保存在公共目录（卸载后仍保留、可手动拷贝换机），
 * Android 11+ 必须拥有 MANAGE_EXTERNAL_STORAGE（特殊权限，无运行时弹窗，
 * 需跳转系统设置页让用户手动开启）。
 */
@CapacitorPlugin(name = "FileAccess")
public class FileAccessPlugin extends Plugin {

    @PluginMethod
    public void isGranted(PluginCall call) {
        JSObject ret = new JSObject();
        boolean granted;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            granted = Environment.isExternalStorageManager();
        } else {
            // Android 10 及以下由运行时存储权限（@capacitor/filesystem）处理
            granted = true;
        }
        ret.put("granted", granted);
        call.resolve(ret);
    }

    @PluginMethod
    public void requestAccess(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                Intent intent = new Intent(
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION
                );
                intent.setData(Uri.parse("package:" + getContext().getPackageName()));
                getActivity().startActivity(intent);
            } catch (Exception e) {
                try {
                    Intent intent = new Intent(
                        Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION
                    );
                    getActivity().startActivity(intent);
                } catch (Exception ignored) {
                    // 设备不支持该设置页，忽略
                }
            }
        }
        call.resolve();
    }
}
