import QtQuick

Rectangle {
    id: root
    property bool isError: false

    function show(msg, err) {
        label.text = msg
        isError = err
        opacity = 1
        hideTimer.restart()
    }

    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 104
    width: label.implicitWidth + 30
    height: 38
    radius: 19
    color: isError ? Theme.errorBg : Theme.toastBg
    border.color: Theme.border
    border.width: 1
    opacity: 0
    Behavior on opacity { NumberAnimation { duration: 200 } }

    Text {
        id: label
        anchors.centerIn: parent
        color: root.isError ? "white" : Theme.text
        font.pixelSize: 12
        font.bold: true
    }

    Timer {
        id: hideTimer
        interval: 2600
        onTriggered: root.opacity = 0
    }
}
