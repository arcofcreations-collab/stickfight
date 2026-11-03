"""choreo.py - reusable fight-choreography generators for stickfight stories (v2).

duel(): a pattern string becomes a beat-locked exchange between two actors A and B.
Every contact lands exactly on its beat; windups start `lead` beats before, and every
strike gets a follow-through key, a whoosh cue and (on contact) a hit-stop.

  one token per `step` beats (some tokens take more steps, noted):
   .  both reset to guard            -  nothing (hold)
   a  A attacks, B blocks (sparks)    b  B attacks, A blocks
   A  A's attack lands on B           B  B's attack lands on A
   k  A kick lands                    K  B kick lands
   x  A big launch hit on B           X  B big launch hit on A
   d  A attacks, B dodges (afterimage back-flip)      D  mirror
   c  both swing: blade clash
   L  blade lock: crossed blades grind, sparks, shove apart (2 steps)
   p  B attacks, A parries and ripostes on the half-beat   P  mirror
   g  A grabs B, throws him over and slams him down; sides swap (2 steps)   G  mirror
   s  A spinning back kick lands      S  mirror
   r  blur-speed trade: four quarter-step strikes with afterimages
   f  A tosses his sword, kicks, catches it and cuts (2 steps)               F  mirror
   z  A knocks B's weapon flying; B leaps and re-catches it (2 steps)       Z  mirror
   j  A launches B, jumps, two air hits, spikes him into a ground bounce (3 steps)  J  mirror
"""
import random

SWORD = [("hi_wind", "hi_cut", "hi"), ("h_wind", "h_cut", "mid"), ("up_wind", "up_cut", "lo"), ("thrust_w", "thrust", "mid"),
         ("h_wind", "spin_cut", "mid")]
HANDS = [("punch_w", "punch", "mid"), ("kick_w", "kick", "mid"), ("kick_w", "hikick", "hi"), ("punch_w", "upper", "hi"),
         ("punch_w", "punch", "hi")]
MIXED = SWORD[:4] + HANDS[:3]
TAKES = {"L": 2, "g": 2, "G": 2, "f": 2, "F": 2, "z": 2, "Z": 2, "j": 3, "J": 3}


def follow(pose_name, k=1.0):
    """an over-extended version of a cut pose, for follow-through."""
    from rig import POSES
    p = dict(POSES[pose_name])
    p["lean"] += 6 * k; p["sF"] += 14 * k; p["w"] += 16 * k; p["head"] += 4 * k
    return p


def duel(st, A, B, b0, pattern, xa, gap=150, step=1.0, seed=0, a_moves=SWORD, b_moves=SWORD, power=1.0, d=1,
         a_guard="guard", b_guard="guard", kb=46, setup=True, air=0.0):
    r = random.Random(seed)
    xb = xa + gap * d
    lead = min(0.45, 0.42 * step)
    b = b0
    if setup:
        A.key(b - lead, pose=a_guard, x=xa, facing=d, air=air, lock=1)
        B.key(b - lead, pose=b_guard, x=xb, facing=-d, air=air, lock=1)
    for tk in pattern:
        if tk == " ": continue
        if tk == "-": b += step; continue
        if tk == ".":
            A.key(b, pose=a_guard, x=xa, ease="smooth"); B.key(b, pose=b_guard, x=xb, ease="smooth")
            b += step; continue
        a_act = tk in "aAkxdcLpgsrfzj"
        att, dfn = (A, B) if a_act else (B, A)
        moves = a_moves if a_act else b_moves
        sgn = d if a_act else -d
        dg = b_guard if a_act else a_guard
        ag = a_guard if a_act else b_guard
        hand_moves = moves is HANDS
        snd = "punch" if hand_moves else "hit"
        # ------------------------------------------------ multi-step specials
        if tk in "LgGfFzZjJsSrpP":
            xatt = xa if a_act else xb; xdef = xb if a_act else xa
            if tk == "L":
                xa = xb - gap * 0.62 * d
                A.key(b - lead, pose="h_wind", x=xa - 10 * d, ease="out"); B.key(b - lead, pose="h_wind", x=xb + 10 * d, ease="out")
                A.key(b, pose="lock", x=xa, ease="snap"); B.key(b, pose="lock", x=xb, ease="snap")
                A.key(b + step * 1.2, pose="lock", x=xa + 14 * d, lean=36); B.key(b + step * 1.2, pose="lock", x=xb - 4 * d, lean=24)
                st.clash_fx(b, (A.name, "tip", (-30, 0)), power * 1.4)
                for q in range(1, 6):
                    st.ev("spark", b + q * step * 0.25, pos=(A.name, "tip", (-35, 0)), n=8, speed=420, color="white")
                st.sfx(b + 0.2 * step, "scrape")
                A.key(b + step * 1.5, pose=a_guard, x=xa - 60 * d, ease="out"); B.key(b + step * 1.5, pose=b_guard, x=xb + 60 * d, ease="out")
                st.clash_fx(b + step * 1.5, (A.name, "tip", (-30, 0)), power * 1.1)
                xa -= 60 * d; xb += 60 * d
                b += 2 * step; continue
            if tk in "pP":
                # attacker = the one who parries (A for p): defender swings first
                swing, rip = (B, A) if tk == "p" else (A, B)
                sg = d if tk == "p" else -d
                xs = xb if tk == "p" else xa; xr = xa if tk == "p" else xb
                mv = r.choice(SWORD[:2])
                swing.key(b - lead, pose=mv[0], ease="out"); swing.key(b, pose=mv[1], ease="snap", x=xs - sg * 10)
                rip.key(b - lead, pose=ag, x=xr); rip.key(b, pose="parry", ease="snap", x=xr - sg * 6)
                st.clash_fx(b, (rip.name, "tip"), power * 1.1)
                rip.key(b + 0.5 * step - 0.15, pose="thrust_w", ease="out")
                rip.key(b + 0.5 * step, pose="thrust", ease="snap", x=xr + sg * 40)
                swing.key(b + 0.5 * step, pose="hit", ease="snap", x=xs + sg * 50); swing.flash(b + 0.5 * step)
                st.hit_fx(b + 0.5 * step, (swing.name, "chest"), power); st.sfx(b + 0.5 * step - 0.12, "whoosh")
                if tk == "p": xa = xr + sg * 40; xb = xs + sg * 50
                else: xb = xr + sg * 40; xa = xs + sg * 50
                b += step; continue
            if tk in "gG":
                xatt = xdef - gap * 0.45 * sgn
                att.key(b - lead, pose="punch_w", x=xatt, ease="out"); att.key(b, pose="grab", ease="snap", x=xatt + 10 * sgn)
                dfn.key(b - lead, pose=dg, x=xdef); dfn.key(b, pose="held", ease="snap", x=xdef - 10 * sgn, air=30)
                st.sfx(b, "punch", -4)
                att.key(b + 0.55 * step, pose="throw", ease="out", x=xatt)
                dfn.key(b + 0.55 * step, pose="held", x=xatt - 10 * sgn, air=170, rot=-140, spin=True, ease="smooth")
                land = xatt - gap * 0.7 * sgn
                dfn.key(b + 1.0 * step, pose="down", x=land, air=0, ease="in", rot=-260, spin=True)
                att.key(b + 1.0 * step, pose="slam", ease="snap", facing=-sgn, x=xatt - 20 * sgn)
                dfn.flash(b + step); st.hit_fx(b + step, (dfn.name, "chest"), power * 1.4, snd="thud")
                st.ev("shock", b + step, pos=(land, 0), size=260); st.ev("crack", b + step, pos=(land, 0), n=6, size=0.8, until=st.T(b + 40))
                st.ev("debris", b + step, pos=(land, 6), n=14, speed=600, size=14); st.ev("dust", b + step, pos=(land, 0), n=8, size=40)
                st.sfx(b + step, "boom", -6)
                dfn.key(b + 1.6 * step, pose="crouch", x=land, rot=-360, spin=True); dfn.key(b + 1.95 * step, pose=dg, x=land)
                att.key(b + 1.95 * step, pose=ag, x=xatt - 20 * sgn, facing=-sgn)
                # sides swapped
                if a_act: xa, xb = xatt - 20 * sgn, land
                else: xb, xa = xatt - 20 * sgn, land
                d = -d
                A.key(b + 1.96 * step, facing=d); B.key(b + 1.96 * step, facing=-d)
                b += 2 * step; continue
            if tk in "sS":
                xatt = xdef - gap * sgn
                att.key(b - lead, pose="spin_back", x=xatt, ease="out", facing=-sgn)
                att.key(b, pose="hikick", ease="snap", x=xatt + 20 * sgn, facing=sgn)
                dfn.key(b - lead, pose=dg, x=xdef)
                dfn.key(b, pose="hit", ease="snap", x=xdef + sgn * 90, xease="out", air=20, arc=10)
                dfn.key(b + 0.6 * step, pose="land", x=xdef + sgn * 130, air=0)
                dfn.flash(b); st.hit_fx(b, (dfn.name, "head"), power * 1.3, snd="punch"); st.sfx(b - 0.15, "whoosh")
                st.afterimages(att.name, b - lead, b, every=0.12, life=0.3, color="ink")
                if a_act: xa, xb = xatt + 20 * sgn, xdef + sgn * 130
                else: xb, xa = xatt + 20 * sgn, xdef + sgn * 130
                b += step; continue
            if tk == "r":
                xa = xb - gap * 0.8 * d
                for q in range(4):
                    bb = b + q * step * 0.25
                    who, oth, sg = (A, B, d) if q % 2 == 0 else (B, A, -d)
                    mv = r.choice(HANDS[:2] + SWORD[:2])
                    who.key(bb - 0.1, pose=mv[0], ease="out"); who.key(bb, pose=mv[1], ease="snap")
                    oth.key(bb, pose="block" if q % 3 else "hit", ease="snap")
                    st.clash_fx(bb, (oth.name, "chest"), power * 0.7, stop=False)
                    st.afterimages(who.name, bb - 0.1, bb, every=0.1, life=0.25, color="red")
                st.ev("speed", b - 0.1, dur=step, angle=0, center=True)
                b += step; continue
            if tk in "fF":
                xatt = xdef - gap * sgn
                att.key(b - lead, pose="guard", x=xatt); att.key(b, pose="toss", ease="snap", armed=False)
                wp = att._at(att.weapons, st.T(b)) or dict(len=96)
                st.ev("prop", b, dur=step * 1.0, p0=(att.name, "hand"), p1=(att.name, "hand", (10, 60)), h=260, spins=3,
                      len=wp.get("len", 96), scale=att.scale, color=wp.get("color"), t1=st.T(b + step * 1.0))
                st.sfx(b, "whoosh", -4)
                att.key(b + 0.5 * step - 0.15, pose="kick_w", x=xatt + 10 * sgn, ease="out")
                att.key(b + 0.5 * step, pose="kick", ease="snap", x=xatt + 20 * sgn)
                dfn.key(b + 0.5 * step, pose="hit", ease="snap", x=xdef + 50 * sgn); dfn.flash(b + 0.5 * step)
                st.hit_fx(b + 0.5 * step, (dfn.name, "chest"), power, snd="punch")
                att.key(b + 1.0 * step, pose="catch", ease="snap", armed=True, x=xatt + 20 * sgn)
                st.sfx(b + step, "draw", -6)
                att.key(b + 1.5 * step - 0.15, pose="hi_wind", ease="out", x=xatt + 30 * sgn)
                att.key(b + 1.5 * step, pose="hi_cut", ease="snap", x=xatt + 60 * sgn)
                dfn.key(b + 1.5 * step, pose="hit_lo", ease="snap", x=xdef + 110 * sgn); dfn.flash(b + 1.5 * step)
                st.hit_fx(b + 1.5 * step, (dfn.name, "chest"), power * 1.3)
                att.key(b + 1.5 * step + 0.2, pose=follow("hi_cut"), ease="out")
                if a_act: xa, xb = xatt + 60 * sgn, xdef + 110 * sgn
                else: xb, xa = xatt + 60 * sgn, xdef + 110 * sgn
                b += 2 * step; continue
            if tk in "zZ":
                xatt = xdef - gap * sgn
                att.key(b - lead, pose="up_wind", x=xatt, ease="out"); att.key(b, pose="up_cut", ease="snap", x=xatt + 14 * sgn)
                dfn.key(b - lead, pose=dg, x=xdef); dfn.key(b, pose="hit", ease="snap", armed=False, x=xdef + 30 * sgn)
                wp = dfn._at(dfn.weapons, st.T(b)) or dict(len=96)
                st.clash_fx(b, (dfn.name, "hand"), power * 1.5)
                catch_x = xdef + 40 * sgn
                st.ev("prop", b, p0=(dfn.name, "hand"), p1=(dfn.name, "hand"), h=420, spins=4, len=wp.get("len", 96),
                      scale=dfn.scale, color=wp.get("color"), t1=st.T(b + 1.5 * step))
                st.sfx(b + 0.1, "whoosh", -2)
                dfn.key(b + 0.9 * step, pose="crouch", x=catch_x)
                dfn.key(b + 1.5 * step, pose="catch", x=catch_x + 10 * sgn, air=140, arc=60, ease="out", armed=True)
                dfn.key(b + 1.95 * step, pose="land", x=catch_x + 20 * sgn, air=0, ease="in")
                st.sfx(b + 1.5 * step, "draw", -4)
                att.key(b + 1.0 * step, pose=ag, x=xatt)
                if a_act: xa, xb = xatt, catch_x + 20 * sgn
                else: xb, xa = xatt, catch_x + 20 * sgn
                b += 2 * step; continue
            if tk in "jJ":
                xatt = xdef - gap * 0.8 * sgn
                att.key(b - lead, pose="up_wind", x=xatt, ease="out"); att.key(b, pose="up_cut", ease="snap", x=xatt + 20 * sgn)
                dfn.key(b - lead, pose=dg, x=xdef)
                dfn.key(b, pose="hit_air", ease="snap", x=xdef + 20 * sgn, air=60)
                dfn.flash(b); st.hit_fx(b, (dfn.name, "chest"), power * 1.3)
                dfn.key(b + 0.75 * step, pose="hit_air", x=xdef + 50 * sgn, air=300, ease="out", rot=-120, spin=True)
                att.key(b + 0.35 * step, pose="crouch", x=xatt + 30 * sgn)
                att.key(b + 0.75 * step - 0.12, pose="h_wind", x=xdef - 40 * sgn, air=260, ease="out")
                att.key(b + 0.75 * step, pose="h_cut", ease="snap", x=xdef - 20 * sgn, air=270)
                dfn.flash(b + 0.75 * step); st.hit_fx(b + 0.75 * step, (dfn.name, "chest"), power)
                dfn.key(b + 1.25 * step, pose="fall", x=xdef + 70 * sgn, air=380, ease="out", rot=-260, spin=True)
                att.key(b + 1.25 * step - 0.12, pose="hi_wind", x=xdef + 30 * sgn, air=420, ease="out")
                att.key(b + 1.25 * step, pose="hi_cut", ease="snap", x=xdef + 50 * sgn, air=400)
                dfn.flash(b + 1.25 * step); st.hit_fx(b + 1.25 * step, (dfn.name, "chest"), power * 1.5)
                st.ev("slashline", b + 1.25 * step, angle=-60, life=0.2, cx=0.5, cy=0.45, width=24, color="red")
                ground = xdef + 110 * sgn
                dfn.key(b + 1.6 * step, pose="down", x=ground, air=0, ease="in", rot=-360, spin=True)
                st.ev("shock", b + 1.6 * step, pos=(ground, 0), size=360); st.ev("crack", b + 1.6 * step, pos=(ground, 0), n=8, size=1.0,
                                                                                until=st.T(b + 60))
                st.ev("debris", b + 1.6 * step, pos=(ground, 6), n=18, speed=700, size=16); st.ev("shake", b + 1.6 * step, amp=26, decay=6)
                st.sfx(b + 1.6 * step, "boom", -2)
                dfn.key(b + 1.9 * step, pose="fall", x=ground + 20 * sgn, air=70, ease="out")          # ground bounce
                dfn.key(b + 2.3 * step, pose="down", x=ground + 40 * sgn, air=0, ease="in")
                st.sfx(b + 2.3 * step, "thud", -6)
                att.key(b + 1.9 * step, pose="land", x=xdef - 10 * sgn, air=0, ease="in")
                dfn.key(b + 2.8 * step, pose="crouch", x=ground + 40 * sgn); dfn.key(b + 2.97 * step, pose=dg, x=ground + 40 * sgn)
                att.key(b + 2.97 * step, pose=ag, x=xdef - 10 * sgn)
                if a_act: xa, xb = xdef - 10 * sgn, ground + 40 * sgn
                else: xb, xa = xdef - 10 * sgn, ground + 40 * sgn
                b += 3 * step; continue
        # ------------------------------------------------ simple tokens
        if tk in "kK": mv = r.choice([m for m in HANDS if "kick" in m[1]])
        elif tk in "xX":
            mv = r.choice([("up_wind", "up_cut", "lo"), ("hi_wind", "hi_cut", "hi")] if not hand_moves
                          else [("punch_w", "upper", "hi"), ("kick_w", "hikick", "hi")])
        else: mv = r.choice(moves)
        wind, cut, height = mv
        snd_here = "punch" if ("punch" in cut or "kick" in cut or cut == "upper") else snd
        if tk == "c":
            mb = r.choice(b_moves)
            A.key(b - lead, pose=wind, ease="out", x=xa); B.key(b - lead, pose=mb[0], ease="out", x=xb)
            A.key(b, pose=cut, ease="snap", x=xa + 10 * d); B.key(b, pose=mb[1], ease="snap", x=xb - 10 * d)
            st.clash_fx(b, (A.name, "tip"), power * 1.5)
            st.sfx(b - 0.12, "whoosh", -6)
            xa -= 22 * d; xb += 22 * d
            A.key(b + 0.4 * step, pose=a_guard, x=xa, xease="out"); B.key(b + 0.4 * step, pose=b_guard, x=xb, xease="out")
            b += step; continue
        if a_act: xa = xb - gap * d
        else: xb = xa + gap * d
        xatt = xa if a_act else xb
        att.key(b - lead, pose=wind, ease="out", x=xatt - sgn * 6)
        att.key(b, pose=cut, ease="snap", x=xatt + sgn * 14)
        if step >= 0.75:
            att.key(b + min(0.3, 0.3 * step), pose=follow(cut), ease="out")
        st.sfx(b - min(0.14, lead * 0.5), "whoosh", -6)
        if a_act: xa += sgn * 14
        else: xb += sgn * 14
        xdef = xb if a_act else xa
        dfn.key(b - lead, pose=dg, x=xdef, ease="smooth")
        if tk in "ab":
            blk = "block_lo" if height == "lo" else "block"
            if dg == "fists": blk = "cross"
            dfn.key(b, pose=blk, ease="snap", x=xdef + sgn * 12)
            st.clash_fx(b, (dfn.name, "mid" if dg != "fists" else "hand"), power)
            xdef += sgn * 12
        elif tk in "AB":
            dfn.key(b, pose="hit" if height != "lo" else "hit_lo", ease="snap", x=xdef + sgn * kb, xease="out")
            dfn.key(b + 0.3 * step, pose="hit", x=xdef + sgn * (kb + 8))
            dfn.flash(b); st.hit_fx(b, (dfn.name, "chest"), power, snd=snd_here)
            xdef += sgn * (kb + 8)
        elif tk in "kK":
            dfn.key(b, pose="hit", ease="snap", x=xdef + sgn * 70, xease="out", air=air + 18, arc=10)
            dfn.key(b + 0.5 * step, pose="land", x=xdef + sgn * 110, air=air)
            dfn.flash(b); st.hit_fx(b, (dfn.name, "chest"), power * 1.2, snd="punch")
            st.ev("dust", b + 0.5 * step, pos=(xdef + sgn * 110, 0), n=6, size=26)
            xdef += sgn * 110
        elif tk in "xX":
            dfn.key(b, pose="hit_air", ease="snap", x=xdef + sgn * 40, air=air + 30)
            land = xdef + sgn * 260
            dfn.key(b + 1.4 * step, pose="land", x=land, air=air, arc=120, xease="out", ease="smooth",
                    rot=-360 if r.random() < 0.5 else 0)
            dfn.flash(b); st.hit_fx(b, (dfn.name, "chest"), power * 1.6, snd=snd_here)
            st.ev("dust", b + 1.4 * step, pos=(land, 0), n=8, size=34)
            st.ev("shock", b + 1.4 * step, pos=(land, 0), size=140)
            st.sfx(b + 1.4 * step, "thud", -4)
            xdef = land
        elif tk in "dD":
            dfn.key(b - 0.1 * step, pose="tuck", ease="out", x=xdef + sgn * 50, air=air + 50, arc=20)
            dfn.key(b + 0.6 * step, pose="land", ease="smooth", x=xdef + sgn * 120, air=air, arc=30, rot=-360)
            st.afterimages(dfn.name, b - 0.35 * step, b + 0.3 * step, every=0.12, life=0.35, color="red")
            st.sfx(b - 0.05, "dodge", -4)
            xdef += sgn * 120
        if a_act: xb = xdef
        else: xa = xdef
        b += step
    A.key(b - lead * 0.5, pose=a_guard, x=xa); B.key(b - lead * 0.5, pose=b_guard, x=xb)
    return xa, xb, b


def minion(st, name, b_spawn, x, facing=-1, drop=0.0, z=-1):
    m = st.actor(name, kind="minion", scale=0.92, z=z)
    m.spawn = st.T(b_spawn)
    m.key(b_spawn, pose="tuck" if drop else "fists", x=x, air=drop, facing=facing, lock=1)
    return m


def civ(st, name, x, facing=1, kid=False, z=-2, pose="stand"):
    a = st.actor(name, kind="kid" if kid else "civ", scale=0.56 if kid else 0.82, z=z)
    a.key(-2, pose=pose, x=x, facing=facing, air=0, lock=1)
    return a


def kill(st, H, M, b, move=("h_wind", "h_cut"), xh=None, gap=120, d=1, kb=150, launch=0.0, lead=0.42, power=1.0,
         die_after=0.7, approach=None, slash=False):
    """H strikes M exactly on beat b; M is thrown back and dissolves into ink."""
    xm = xh + gap * d
    if approach is not None:      # minion sprints in from `approach` x
        M.key(b - 2.4, pose="fists", x=approach, facing=-d, air=0, lock=1)
        M.run(b - 2.4, b - lead, xm, kind="ninja", pose_end="fists")
    else:
        M.key(b - lead, pose="fists", x=xm, facing=-d, air=0, lock=1)
    H.key(b - lead, pose=move[0], x=xh - 8 * d, facing=d, ease="out")
    H.key(b, pose=move[1], ease="snap", x=xh + 12 * d)
    H.key(b + 0.25, pose=follow(move[1], 0.8), ease="out")
    st.sfx(b - 0.12, "whoosh", -6)
    M.key(b, pose="hit_air" if launch else "hit", ease="snap", x=xm + d * 30, air=10 if launch else 0)
    M.key(b + die_after, pose="fall", x=xm + d * kb, air=launch * 0.6, arc=launch + 30, xease="out",
          rot=-200 if launch else -60)
    M.flash(b)
    st.hit_fx(b, (M.name, "chest"), power, snd="punch" if ("kick" in move[1] or "punch" in move[1] or move[1] == "upper") else "hit")
    if slash:
        st.ev("slashline", b, angle=-22, life=0.16, cx=0.5, cy=0.5)
    M.die = st.T(b + die_after)
    st.ev("ink", b + die_after, pos=(M.name, "chest"), n=22, speed=300)
    st.ev("dust", b + die_after, pos=(M.name, "chest"), n=6, size=30)
    return xh + 12 * d


def power_up(st, actor, b_charge, b_release, x, level=2.0, color=(206, 22, 44), sky_invert=True, radius=520, hold=8,
             burst=True, eyes_shot=None):
    """the full anime power-up beat: rumble + floating rocks + cracks during the charge, slow-mo into the release,
    then a screen-filling burst, inverted colour, rocks blasted out, and the aura held for `hold` beats."""
    a = st.actors[actor] if isinstance(actor, str) else actor
    st.ev("rumble", b_charge, dur=b_release - b_charge, amp=4)
    st.ev("lift", b_charge, x=x, t_release=st.T(b_release), radius=radius, n=30, blast=1500)
    for k in range(4):
        st.ev("crack", b_charge + k * (b_release - b_charge) / 4, pos=(x + (k - 1.5) * 90, 0), n=5, size=0.9 + 0.2 * k,
              until=st.T(b_release + hold + 8), red=True)
    a.powerup(b_charge, b_release, level * 0.45, color)
    a.powerup(b_release, b_release + hold, level, color)
    st.slowmo(b_release, w=1.0, r=0.18)
    st.sfx(b_charge, "rumble", 0); st.sfx(b_release, "boom", 2); st.sfx(b_release, "power", 0)
    if burst:
        st.ev("burst", b_release, pos=(a.name, "chest"), size=2600, life=0.8)
        st.ev("impact", b_release + 0.05, frames=3)
    st.ev("shock", b_release, pos=(x, 0), size=900, flat=0.3)
    st.ev("shake", b_release, amp=36, decay=3.5)
    st.ev("debris", b_release, pos=(x, 8), n=30, speed=1100, size=18)
    st.ev("dust", b_release, pos=(x, 0), n=14, size=90)
