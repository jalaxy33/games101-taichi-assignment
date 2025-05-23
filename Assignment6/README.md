# 作业 6. BVH 加速结构

在之前实现的 Whitted-style Raytracer 的基础上，实现 BVH 加速结构以及 SAH 结构划分优化方法。


**关键词**：BVH, SAH

**参考资料**：
- 《虎书》 第 12 章（Data Structure for Graphics）
- 《Games101》[Lecture 14](https://sites.cs.ucsb.edu/~lingqi/teaching/resources/GAMES101_Lecture_14.pdf)
- 《Physically Based Rendering》 [4.3 Bounding Volume Hierarchies](https://www.pbr-book.org/3ed-2018/Primitives_and_Intersection_Acceleration/Bounding_Volume_Hierarchies), [2.6 Bounding Boxes](https://www.pbr-book.org/3ed-2018/Geometry_and_Transformations/Bounding_Boxes)
- 参考实现：
    - [mmoon/taichi-rt](https://gitee.com/mmoon/taichi-rt/blob/master/ti_rt/utils/model.py)
    - [lyd405121/ti-raytrace](https://github.com/lyd405121/ti-raytrace/blob/main/accel/SahBvh.py)
    - [bsavery/ray-tracing-one-weekend-taichi](https://github.com/bsavery/ray-tracing-one-weekend-taichi/blob/main/bvh.py)
    - [lyd405121/ti-bvh](https://github.com/lyd405121/ti-bvh)


**题解**：[main.py](./main.py)



![](./imgs/BVH%20RayTracing.png)





