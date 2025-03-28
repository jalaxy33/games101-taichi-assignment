import taichi as ti
import taichi.math as tm

from models import *


# Define task types
TASK_PROCESS = 0  # Process a material
TASK_MERGE = 1  # Merge results from REFLECT_AND_REFRACT


Color = ti.types.vector(3, ti.f32)


@ti.func
def rand3():
    return ti.Vector([ti.random(), ti.random(), ti.random()])


@ti.func
def random_in_unit_sphere():
    p = 2.0 * rand3() - ti.Vector([1, 1, 1])
    while p.norm() >= 1.0:
        p = 2.0 * rand3() - ti.Vector([1, 1, 1])
    return p


@ti.func
def random_unit_vector():
    return random_in_unit_sphere().normalized()


@ti.dataclass
class AmbientLight:
    Ia: tm.vec3


@ti.dataclass
class PointLight:
    pos: tm.vec3  # position
    I: tm.vec3  # Intensity


@ti.data_oriented
class LightList:
    def __init__(self):
        self.ambient_light = AmbientLight()
        self.point_lights = []

    def add_ambient_light(self, intensity: tm.vec3):
        self.ambient_light.Ia = tm.vec3(intensity)

    def add_point_light(self, pos: tm.vec3, intensity: tm.vec3):
        self.point_lights.append(PointLight(tm.vec3(pos), tm.vec3(intensity)))


@ti.data_oriented
class HittableList:
    def __init__(self):
        self.objs = []

    def clear(self):
        self.objs.clear()

    def add(self, obj):
        self.objs.append(obj)

    @ti.func
    def hit(self, ray: Ray, tmin=tm.inf) -> HitRecord:
        rec = HitRecord()
        closest_so_far = tmin

        for i in ti.static(range(len(self.objs))):
            temp_rec = self.objs[i].hit(ray, closest_so_far)
            if temp_rec.is_hit and temp_rec.t < closest_so_far:
                closest_so_far = temp_rec.t
                rec = temp_rec

        return rec


@ti.dataclass
class StatusFrame:
    task_type: ti.i32
    depth: ti.i32
    ray: Ray
    kr: ti.f32


@ti.data_oriented
class StatusStack:
    def __init__(self, width, height, max_depth):
        self.max_depth = max_depth
        self.stack = StatusFrame.field(shape=(width, height, max_depth))
        self.ptr = ti.field(ti.i32, shape=(width, height))

        self.ptr.fill(-1)

    @ti.func
    def clear(self, i, j):
        self.ptr[i, j] = -1

    @ti.func
    def empty(self, i, j) -> bool:
        return self.ptr[i, j] <= -1

    @ti.func
    def full(self, i, j) -> bool:
        return self.ptr[i, j] >= self.max_depth

    @ti.func
    def top(self, i, j):
        return self.stack[i, j, self.ptr[i, j]]

    @ti.func
    def push(self, i, j, value) -> bool:
        succeed = False
        if self.ptr[i, j] + 1 < self.max_depth:
            succeed = True
            self.ptr[i, j] += 1
            self.stack[i, j, self.ptr[i, j]] = value
        return succeed

    @ti.func
    def pop(self, i, j) -> bool:
        succeed = False
        if self.ptr[i, j] - 1 >= -1:
            succeed = True
            self.ptr[i, j] -= 1
        return succeed


@ti.data_oriented
class ResultStack:
    def __init__(self, width, height, max_depth):
        self.max_depth = max_depth
        self.stack = ti.field(Color, shape=(width, height, max_depth))
        self.ptr = ti.field(ti.i32, shape=(width, height))

        self.ptr.fill(-1)

    @ti.func
    def clear(self, i, j):
        self.ptr[i, j] = -1

    @ti.func
    def empty(self, i, j) -> bool:
        return self.ptr[i, j] <= -1

    @ti.func
    def full(self, i, j) -> bool:
        return self.ptr[i, j] >= self.max_depth

    @ti.func
    def top(self, i, j):
        return self.stack[i, j, self.ptr[i, j]]

    @ti.func
    def push(self, i, j, value) -> bool:
        succeed = False
        if self.ptr[i, j] + 1 < self.max_depth:
            succeed = True
            self.ptr[i, j] += 1
            self.stack[i, j, self.ptr[i, j]] = value
        return succeed

    @ti.func
    def pop(self, i, j) -> bool:
        succeed = False
        if self.ptr[i, j] - 1 >= -1:
            succeed = True
            self.ptr[i, j] -= 1
        return succeed


@ti.data_oriented
class Renderer:
    def __init__(
        self,
        width,
        height,
        background_color=(0.235294, 0.67451, 0.843137),
        max_depth=10,
        max_stack_size=50,
        vfov=90,
        eye_pos=(0, 0, 0),
        reflect_fuzz=0.1,
    ):
        self.W = width
        self.H = height
        self.frame_buf = ti.Vector.field(3, ti.f32, shape=(width, height))
        self.background_color = tm.vec3(background_color)
        self.max_depth = max_depth
        self.max_stack_size = max_stack_size
        self.vfov = vfov
        self.eye_pos = tm.vec3(eye_pos)
        self.reflect_fuzz = reflect_fuzz

        self.lights = LightList()
        self.world = HittableList()

        self.status_stack = StatusStack(width, height, max_stack_size)
        self.result_stack = ResultStack(width, height, max_stack_size)

    @ti.func
    def reflect(self, v, n):
        return v - 2 * v.dot(n) * n

    @ti.func
    def refract(self, v, n, etai_over_etat):
        cos_theta = min(n.dot(-v), 1.0)
        r_out_perp = etai_over_etat * (v + cos_theta * n)
        r_out_parallel = -ti.sqrt(abs(1.0 - r_out_perp.dot(r_out_perp))) * n
        return r_out_perp + r_out_parallel

    @ti.func
    def reflectance(self, cosine, ref_idx):
        # Use Schlick's approximation for reflectance.
        r0 = (1 - ref_idx) / (1 + ref_idx)
        r0 = r0 * r0
        return r0 + (1 - r0) * pow((1 - cosine), 5)

    @ti.func
    def bling_phong(self, ray: Ray, rec: HitRecord):
        eps = 1e-5
        shadow_orig = rec.pos + rec.N * eps if tm.dot(ray.rd, rec.N) < 0 else rec.pos - rec.N * eps

        color = tm.vec3(0)
        ambient_color = tm.vec3(0)
        diffuse_color = tm.vec3(0)
        specular_color = tm.vec3(0)
        for i in ti.static(range(len(self.lights.point_lights))):
            light = self.lights.point_lights[i]

            r = tm.distance(light.pos, rec.pos)  # 光源-点距离
            light_dir = (light.pos - rec.pos).normalized()  # 光源-点方向

            shadow_rec = self.world.hit(Ray(shadow_orig, light_dir), tm.inf)
            in_shadow = shadow_rec.is_hit and shadow_rec.t < r

            # ambient
            ambient_color = rec.mat.ka * self.lights.ambient_light.Ia

            # diffuse
            diffuse_color += tm.vec3(0) if in_shadow else max(0, tm.dot(light_dir, rec.N))

            # specular
            reflect_dir = self.reflect(-light_dir, rec.N).normalized()
            specular_color += light.I * tm.pow(tm.max(0, -tm.dot(reflect_dir, light_dir)), rec.mat.spec_exp)

        color = ambient_color + rec.mat.kd * rec.mat.diffuse_color * diffuse_color + rec.mat.ks * specular_color

        return color

    @ti.kernel
    def render(self):
        aspect_ratio = 1.0 * self.W / self.H
        half_height = tm.tan(tm.radians(self.vfov / 2))
        half_width = half_height * aspect_ratio

        for i, j in self.frame_buf:
            # TODO: Find the x and y positions of the current pixel to get the direction
            # vector that passes through it.
            # Also, don't forget to multiply both of them with the variable *scale*, and
            # x (horizontal) variable with the *imageAspectRatio*

            x = ((i + ti.random()) / self.W - 0.5) * 2 * half_width
            y = ((j + ti.random()) / self.H - 0.5) * 2 * half_height

            ray_direction = tm.vec3(x, y, -1).normalized()
            ray = Ray(self.eye_pos, ray_direction)

            pixel_color = self.ray_color(i, j, ray)

            self.frame_buf[i, j] = pixel_color

    # Whitted-style RayTracer
    @ti.func
    def ray_color(self, i, j, ray: Ray):
        pixel_color = tm.vec3(0)
        eps = 1e-5

        self.status_stack.clear(i, j)
        self.result_stack.clear(i, j)

        frame = StatusFrame(task_type=TASK_PROCESS, depth=0, ray=ray, kr=1.0)
        self.status_stack.push(i, j, frame)
        while not self.status_stack.empty(i, j):
            frame = self.status_stack.top(i, j)
            self.status_stack.pop(i, j)

            if frame.task_type == TASK_PROCESS:
                if frame.depth >= self.max_depth:
                    self.result_stack.push(i, j, Color(0, 0, 0))
                    continue

                rec = self.world.hit(frame.ray, tm.inf)
                rd = frame.ray.rd.normalized()
                m_type = rec.mat.m_type
                depth = frame.depth

                if rec.is_hit:
                    if m_type == REFLECTION_AND_REFRACTION or m_type == REFLECTION:
                        ref_idx = rec.mat.ior
                        if rec.front_face:
                            ref_idx = 1.0 / ref_idx

                        cos_theta = max(min(-rd.dot(rec.N), 1.0), -1.0)
                        kr = self.reflectance(cos_theta, ref_idx)

                        reflect_dir = self.reflect(rd, rec.N).normalized()
                        reflect_dir += self.reflect_fuzz * random_unit_vector()

                        reflect_orig = rec.pos
                        if reflect_dir.dot(rec.N) > 0:
                            reflect_orig += rec.N * eps
                        else:
                            reflect_orig += rec.N * eps

                        merge_frame = StatusFrame(task_type=TASK_MERGE, depth=depth + 1, kr=kr)
                        self.status_stack.push(i, j, merge_frame)

                        reflect_frame = StatusFrame(
                            task_type=TASK_PROCESS,
                            depth=depth + 1,
                            ray=Ray(reflect_orig, reflect_dir),
                        )
                        self.status_stack.push(i, j, reflect_frame)

                        if m_type == REFLECTION_AND_REFRACTION:
                            refract_dir = self.refract(rd, rec.N, ref_idx).normalized()
                            refract_orig = rec.pos
                            if refract_dir.dot(rec.N) > 0:
                                refract_orig += rec.N * eps
                            else:
                                refract_orig -= rec.N * eps

                            refract_frame = StatusFrame(
                                task_type=TASK_PROCESS,
                                depth=depth + 1,
                                ray=Ray(refract_orig, refract_dir),
                            )
                            self.status_stack.push(i, j, refract_frame)
                        else:  # m_type == REFLECTION
                            self.result_stack.push(i, j, Color(self.background_color * 0.99))

                    else:
                        # [comment]
                        # We use the Phong illumation model int the default case. The phong model
                        # is composed of a diffuse and a specular reflection component.
                        # [/comment]
                        color = self.bling_phong(frame.ray, rec)
                        self.result_stack.push(i, j, color)
                else:
                    break

            elif frame.task_type == TASK_MERGE:
                kr = frame.kr
                refract_color = self.result_stack.top(i, j)
                self.result_stack.pop(i, j)
                reflect_color = self.result_stack.top(i, j)
                self.result_stack.pop(i, j)

                combined_color = kr * reflect_color + (1 - kr) * refract_color
                self.result_stack.push(i, j, combined_color)

        if not self.result_stack.empty(i, j):
            pixel_color = self.result_stack.top(i, j)
            self.result_stack.pop(i, j)
        else:
            pixel_color = self.background_color

        return pixel_color
