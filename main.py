import pygame
import random
import sys
import math
import json
from pathlib import Path

pygame.init()
pygame.mixer.init()

# --- Config ---
WIDTH, HEIGHT = 800, 600
CELL = 20
ASSETS_DIR = Path("Assets")

# Sound filenames (place sounds here)
BGM_FILE = ASSETS_DIR / "bgm.mp3"
SND_EAT = ASSETS_DIR / "eat.mp3"
SND_LEVEL = ASSETS_DIR / "levelup.mp3"
SND_PAUSE = ASSETS_DIR / "pause.mp3"
SND_GAMEOVER = ASSETS_DIR / "dead.mp3"

# Colors
BG_TOP = (10, 12, 20)
BG_BOTTOM = (30, 36, 50)
SNAKE_COLOR = (0, 200, 120)
FOOD_COLOR = (255, 180, 0)
OBSTACLE_COLOR = (200, 50, 50)
TEXT_COLOR = (240, 240, 240)
ACCENT = (120, 200, 255)

# UI
FONT = pygame.font.SysFont("consolas", 20)
BIG_FONT = pygame.font.SysFont("consolas", 56)
SMALL_FONT = pygame.font.SysFont("consolas", 14)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Snake — Audio Polished Version")
clock = pygame.time.Clock()

# --- Helpers: sounds safe load ---
def load_sound(path):
    try:
        return pygame.mixer.Sound(str(path))
    except Exception as e:
        print(f"[WARN] failed load sound {path}: {e}")
        return None

bgm = None
if BGM_FILE.exists():
    try:
        pygame.mixer.music.load(str(BGM_FILE))
    except Exception as e:
        print("Can't load music:", e)
eat_sound = load_sound(SND_EAT) 
level_sound = load_sound(SND_LEVEL)
pause_sound = load_sound(SND_PAUSE)
gameover_sound = load_sound(SND_GAMEOVER)

# volume control
master_vol = 0.7
def apply_volume(v):
    global master_vol
    master_vol = max(0.0, min(1.0, v))
    pygame.mixer.music.set_volume(master_vol)
    for s in (eat_sound, level_sound, pause_sound, gameover_sound):
        if s: s.set_volume(master_vol)

apply_volume(master_vol)

# --- Game data / persistence ---
HS_FILE = Path("highscore.json")
def load_highscore():
    if HS_FILE.exists():
        try:
            return json.loads(HS_FILE.read_text()).get("highscore", 0)
        except:
            return 0
    return 0
def save_highscore(h):
    HS_FILE.write_text(json.dumps({"highscore": h}))

highscore = load_highscore()

# --- Particle system (simple circles) ---
class Particle:
    def __init__(self, x, y, vx, vy, life, size, color):
        self.x = x; self.y = y
        self.vx = vx; self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size
        self.color = color
    def update(self, dt):
        self.life -= dt
        self.x += self.vx * dt * 60
        self.y += self.vy * dt * 60
    def draw(self, surf, offset=(0,0)):
        if self.life <= 0: return
        alpha = max(0, int(255 * (self.life / self.max_life)))
        s = pygame.Surface((self.size*2, self.size*2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (self.size, self.size), self.size)
        surf.blit(s, (int(self.x - self.size + offset[0]), int(self.y - self.size + offset[1])))

particles = []

# --- Floating score pop text ---
class FloatText:
    def __init__(self, text, x, y, color=ACCENT):
        self.text = text; self.x=x; self.y=y; self.life=1.0; self.color=color
    def update(self, dt):
        self.y -= 30 * dt
        self.life -= dt
    def draw(self, surf, offset=(0,0)):
        if self.life <= 0: return
        alpha = max(0, int(255*self.life))
        s = SMALL_FONT.render(self.text, True, self.color)
        s.set_alpha(alpha)
        surf.blit(s, (self.x + offset[0], self.y + offset[1]))
float_texts = []

# --- Basic game classes ---
class Snake:
    def __init__(self):
        self.body = [[200,200],[180,200],[160,200]]
        self.direction = "RIGHT"
    def move(self):
        head = self.body[0].copy()
        if self.direction == "UP": head[1] -= CELL
        if self.direction == "DOWN": head[1] += CELL
        if self.direction == "LEFT": head[0] -= CELL
        if self.direction == "RIGHT": head[0] += CELL
        head[0] %= WIDTH
        head[1] %= HEIGHT
        self.body.insert(0, head)
        self.body.pop()
    def grow(self):
        self.body.append(self.body[-1].copy())
    def draw(self, surf, offset=(0,0)):
        for i, part in enumerate(self.body):
            r = pygame.Rect(part[0]+offset[0], part[1]+offset[1], CELL, CELL)
            # slight inset for nicer look
            inner = r.inflate(-4, -4)
            pygame.draw.rect(surf, SNAKE_COLOR, inner, border_radius=6)

class Food:
    def __init__(self):
        self.pos = self.random_pos()
        self.time = 0.0
    def random_pos(self):
        return [
            random.randrange(0, WIDTH//CELL) * CELL,
            random.randrange(0, HEIGHT//CELL) * CELL
        ]
    def draw(self, surf, offset=(0,0)):
        # pulsing circle (no sprite)
        self.time += 0.05
        pulse = 4 * math.sin(self.time*6)
        cx = self.pos[0] + CELL//2 + offset[0]
        cy = self.pos[1] + CELL//2 + offset[1]
        pygame.draw.circle(surf, FOOD_COLOR, (cx, cy), CELL//2 + int(pulse))
        # highlight
        pygame.draw.circle(surf, (255,255,255,40), (cx-6, cy-8), 6)

class Obstacle:
    def __init__(self, amount):
        self.blocks = []
        for _ in range(amount):
            self.blocks.append([random.randrange(0, WIDTH // CELL) * CELL,
                                random.randrange(0, HEIGHT // CELL) * CELL])
    def draw(self, surf, offset=(0,0)):
        for b in self.blocks:
            r = pygame.Rect(b[0]+offset[0], b[1]+offset[1], CELL, CELL)
            inner = r.inflate(-4, -4)
            pygame.draw.rect(surf, OBSTACLE_COLOR, inner, border_radius=4)

# --- UI drawing helpers ---
def draw_gradient_bg(surf):
    # top to bottom gradient
    for i in range(HEIGHT):
        t = i / HEIGHT
        r = int(BG_TOP[0]*(1-t) + BG_BOTTOM[0]*t)
        g = int(BG_TOP[1]*(1-t) + BG_BOTTOM[1]*t)
        b = int(BG_TOP[2]*(1-t) + BG_BOTTOM[2]*t)
        pygame.draw.line(surf, (r,g,b), (0,i),(WIDTH,i))

def draw_hud(score, level, vol):
    txt = FONT.render(f"Score: {score}    Level: {level}    High: {highscore}", True, TEXT_COLOR)
    screen.blit(txt, (10, 8))
    vol_txt = SMALL_FONT.render(f"Vol: {int(vol*100)}%  (M mute, + / -)", True, TEXT_COLOR)
    screen.blit(vol_txt, (WIDTH-220, 10))

# --- screen shake state ---
shake_time = 0.0
shake_intensity = 0.0
def start_shake(inten=6.0, duration=0.4):
    global shake_time, shake_intensity
    shake_time = duration
    shake_intensity = inten

def compute_shake_offset():
    global shake_time
    if shake_time > 0:
        shake_time -= dt
        ox = random.uniform(-shake_intensity, shake_intensity)
        oy = random.uniform(-shake_intensity, shake_intensity)
        return int(ox), int(oy)
    return 0,0

# --- Game states & flow ---
def start_screen():
    pygame.mixer.music.stop()
    if pause_sound: pause_sound.play()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_SPACE:
                    # start BGM
                    try:
                        pygame.mixer.music.play(-1)
                    except:
                        pass
                    return
                if e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
        draw_gradient_bg(screen)
        title = BIG_FONT.render("SNAKE RETRO", True, ACCENT)
        sub = FONT.render("Press SPACE to start  •  M mute  •  + / - volume", True, TEXT_COLOR)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 180))
        screen.blit(sub, (WIDTH//2 - sub.get_width()//2, 260))
        pygame.display.update()
        clock.tick(30)

def game_over_screen(score):
    pygame.mixer.music.stop()
    if gameover_sound: gameover_sound.play()
    save_highscore(max(highscore, score))
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_r:
                    return
                if e.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
        draw_gradient_bg(screen)
        txt = BIG_FONT.render("GAME OVER", True, (255,120,120))
        s2 = FONT.render(f"Score: {score}   High: {max(highscore, score)}", True, TEXT_COLOR)
        s3 = FONT.render("Press R to Restart or ESC to Quit", True, TEXT_COLOR)
        screen.blit(txt, (WIDTH//2 - txt.get_width()//2, 180))
        screen.blit(s2, (WIDTH//2 - s2.get_width()//2, 260))
        screen.blit(s3, (WIDTH//2 - s3.get_width()//2, 320))
        pygame.display.update()
        clock.tick(30)

# --- Main game loop (with sound & polish) ---
def main_loop():
    global dt, highscore
    snake = Snake()
    food = Food()
    level = 1
    score = 0
    speed = 8
    obstacle = Obstacle(level)
    paused = False
    last_move_time = 0.0
    move_interval = 0.12  # seconds between grid moves -> speed affects this

    # start music if available
    try:
        pygame.mixer.music.play(-1)
    except: pass

    running = True
    while running:
        dt = clock.tick(60) / 1000.0  # delta seconds
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_p:
                    paused = not paused
                    if pause_sound: pause_sound.play()
                if e.key == pygame.K_m:
                    # mute toggle
                    if master_vol > 0:
                        apply_volume(0)
                    else:
                        apply_volume(0.7)
                if e.key == pygame.K_PLUS or e.key == pygame.K_EQUALS:
                    apply_volume(master_vol + 0.1)
                if e.key == pygame.K_MINUS:
                    apply_volume(master_vol - 0.1)
                if e.key == pygame.K_UP and snake.direction != "DOWN":
                    snake.direction = "UP"
                if e.key == pygame.K_DOWN and snake.direction != "UP":
                    snake.direction = "DOWN"
                if e.key == pygame.K_LEFT and snake.direction != "RIGHT":
                    snake.direction = "LEFT"
                if e.key == pygame.K_RIGHT and snake.direction != "LEFT":
                    snake.direction = "RIGHT"

        if paused:
            draw_gradient_bg(screen)
            paused_txt = BIG_FONT.render("PAUSED", True, ACCENT)
            screen.blit(paused_txt, (WIDTH//2 - paused_txt.get_width()//2, HEIGHT//2-40))
            draw_hud(score, level, master_vol)
            pygame.display.update()
            continue

        # move snake on fixed interval (so audio sync feels consistent)
        last_move_time += dt
        if last_move_time >= move_interval:
            snake.move()
            last_move_time = 0.0

        # Eat food?
        if snake.body[0] == food.pos:
            snake.grow()
            food.pos = food.random_pos()
            score += 1
            # spawn particles
            hx = snake.body[0][0] + CELL/2
            hy = snake.body[0][1] + CELL/2
            for _ in range(18):
                vx = random.uniform(-2,2)
                vy = random.uniform(-3,1)
                particles.append(Particle(hx, hy, vx, vy, 0.8+random.random()*0.6, random.randint(3,8), FOOD_COLOR))
            float_texts.append(FloatText("+1", hx, hy - 12))
            if eat_sound: eat_sound.play()
            # level up tiap 5 skor
            if score % 5 == 0:
                level += 1
                # speed up slightly (reduce move interval)
                move_interval = max(0.05, move_interval * 0.88)
                obstacle = Obstacle(level)
                if level_sound: level_sound.play()
                # increase music pitch/intensity if you like (not trivial in pygame), we modulate volume briefly
                if pygame.mixer.music.get_busy():
                    old = pygame.mixer.music.get_volume()
                    pygame.mixer.music.set_volume(min(1.0, old + 0.06))

        # collisions
        if snake.body[0] in snake.body[1:]:
            if gameover_sound: gameover_sound.play()
            start_shake(10.0, 0.5)
            highscore = max(highscore, score)
            return score
        if snake.body[0] in obstacle.blocks:
            if gameover_sound: gameover_sound.play()
            start_shake(12.0, 0.6)
            highscore = max(highscore, score)
            return score

        # update particles and floats
        for p in particles[:]:
            p.update(dt)
            if p.life <= 0:
                particles.remove(p)
        for f in float_texts[:]:
            f.update(dt)
            if f.life <= 0:
                float_texts.remove(f)

        # compute shake offset
        offset = compute_shake_offset()

        # draw
        draw_gradient_bg(screen)
        snake.draw(screen, offset)
        food.draw(screen, offset)
        obstacle.draw(screen, offset)
        for p in particles:
            p.draw(screen, offset)
        for f in float_texts:
            f.draw(screen, offset)
        draw_hud(score, level, master_vol)

        pygame.display.update()

    return 0

# --- Run flow ---
while True:
    start_screen()
    # play bgm loop if exists
    try:
        pygame.mixer.music.set_volume(master_vol)
        pygame.mixer.music.play(-1)
    except: pass
    final = main_loop()
    game_over_screen(final)
