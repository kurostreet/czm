/* Kinetic scrolling for our touch lists (the map vote window).
 *
 * Follows the finger 1:1 from the moment it starts to drag (no jump by the touch slop),
 * keeps a flick going after the finger lifts and slows it down, glides to a place asked
 * for (a tapped row, the wheel), and tells a tap from a drag or from catching a moving list.
 * Positions are pixels of the list content; time is seconds. */
#pragma once
#include <cmath>

namespace CzmScroll {

struct List {
    float pos, max, velocity, target, slop;
    bool down, dragging, caught, aiming;
    float downY, anchorY, anchorPos, lastY;
    double lastTime;

    List() : pos(0), max(0), velocity(0), target(0), slop(12), down(false), dragging(false), caught(false),
        aiming(false), downY(0), anchorY(0), anchorPos(0), lastY(0), lastTime(0) {}

    float Bound(float p) const { return p < 0 ? 0 : p > max ? max : p; }
    void Clamp() {
        const float b = Bound(pos);
        if (b != pos) { pos = b; velocity = 0; }
        if (aiming) target = Bound(target);
    }
    void SetMax(float m) { max = m > 0 ? m : 0; Clamp(); }

    void Press(float y, double now) {
        caught = std::fabs(velocity) > 150.0f; // a finger that stops a moving list does not tap
        down = true; dragging = false; aiming = false; velocity = 0;
        downY = lastY = y; lastTime = now;
    }
    void Move(float y, double now) {
        if (!down) return;
        if (!dragging && std::fabs(y - downY) > slop) { dragging = true; anchorY = y; anchorPos = pos; }
        if (dragging) {
            pos = Bound(anchorPos - (y - anchorY));
            const double dt = now - lastTime;
            if (dt > 0.001) velocity = velocity * 0.3f + (float)(-(y - lastY) / dt) * 0.7f;
        }
        lastY = y; lastTime = now;
    }
    // true when the touch was a tap
    bool Release(double now) {
        const bool tap = !dragging && !caught;
        if (!dragging || now - lastTime > 0.08) velocity = 0; // a finger that stopped does not fling
        down = dragging = caught = false;
        return tap;
    }

    void ScrollTo(float p) { target = Bound(p); aiming = true; velocity = 0; }
    void Wheel(float delta) { ScrollTo((aiming ? target : pos) + delta); }
    // brings [top, bottom] of the content into a view `view` pixels high
    void Reveal(float top, float bottom, float view) {
        const float from = aiming ? target : pos;
        float p = from;
        if (top < p) p = top;
        else if (bottom > p + view) p = bottom - view;
        if (p != from) ScrollTo(p);
    }

    void Step(double dt) {
        if (down || dt <= 0) return;
        if (dt > 0.1) dt = 0.1;
        if (velocity != 0) {
            pos += velocity * (float)dt;
            velocity *= (float)std::exp(-3.5 * dt);
            if (std::fabs(velocity) < 20.0f) velocity = 0;
        } else if (aiming) {
            pos += (target - pos) * (float)(1.0 - std::exp(-14.0 * dt));
            if (std::fabs(target - pos) < 0.5f) { pos = target; aiming = false; }
        }
        Clamp();
    }
};

// A row glides to its new place in the list instead of jumping there.
inline float Glide(float from, float to, double dt) {
    if (dt <= 0) return from;
    if (dt > 0.1) dt = 0.1;
    const float next = from + (to - from) * (float)(1.0 - std::exp(-12.0 * dt));
    return std::fabs(to - next) < 0.002f ? to : next;
}

}
